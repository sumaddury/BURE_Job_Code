```psuedocode
Algorithm sampling_pipeline(AST_Dict):
    FUNC_Dict, Flaky_Assertions <- AssertSpecFinder(AST_DICT)
    L <- empty list
    for each Assertion in Flaky_Assertions:
        Logged_Test <- Instrumentor(FUNC_Dict, AST_Dict, Assertion)
        write Logged_Test to file
        L.append(Logged_Test)
    add L as column to Flaky_Assertions
    set up new conda environment
    install dependencies
    configs <- seeding configs
    data <- empty list
    for each Logged_Test in Flaky_Assertions:
        for each config in configs:
            pass config to conftest
            temp_data <- sample test for 100 trials
            data.append(temp_data)
    return data
```

Problem test indexes:
15,16,17,25,26,27,31,38,45,46,47,48,51,55

Indexes to run:


commands:
```bash

# rm -rf lightning_repo
mkdir -p ast_dir
python3 AssertSpecFinder.py compile --project-link https://github.com/Lightning-AI/pytorch-lightning.git \
    --clone-dir lightning_repo \
    --asts-out ast_dir/lightning_asts.pkl

mkdir -p test_csvs
python3 AssertSpecFinder.py mine --asts-in ast_dir/lightning_asts.pkl \
    --csv-target test_csvs/lightning_assertions.csv \
    --funcs-out ast_dir/lightning_funcs.pkl

# deactivate
# rm -rf .venv
python3.10 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements_custom.txt

# cd lightning_repo
# make test
# cd ..

pip freeze > constraints.txt
pip install -r script_reqs.txt \
    --constraint constraints.txt

python3 Seeder.py remove_seed --asts-in ast_dir/lightning_asts.pkl

python3 Instrumentor.py log --csv-in test_csvs/lightning_assertions.csv \
    --csv-out test_csvs/lightning_assertions_m1.csv \
    --asts-in ast_dir/lightning_asts.pkl \
    --funcs-in ast_dir/lightning_funcs.pkl

cp conftest.py lightning_repo/

# rm -rf lightning_dists
mkdir -p lightning_dists

python3 Distributions.py sample_csv --csv-in test_csvs/lightning_assertions_m1.csv \
    --dir-out lightning_dists \
    --assertions "test_full_loop_244,test_full_loop_249,test_train_loop_only_168,test_train_val_loop_only_185" \
    --repo-name lightning_repo \
    --seed-value 42 \
    --seed-config-file-in ../seed_configs.yaml \
    --seed-config-names "NO_SEEDS;RANDOM;NUMPY;TORCH;RANDOM,NUMPY,TORCH"
```

Building:
```bash
docker login
docker buildx create --use
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --push \
  -t cygenta123/pl-pipeline:latest \
  -f containers/Dockerfile .

```
G2 commands:
```bash
ssh sm2939@g2-login.coecis.cornell.edu

git clone https://github.com/sumaddury/BURE_Job_Code.git
cd BURE_Job_Code
mkdir -p logs
sbatch jobs/convert.sub cygenta123/pl-pipeline:latest flaky-sandbox


mkdir -p /share/dutta/$USER/containers
mv pl-pipeline.sif     /share/dutta/$USER/containers/
mv flaky-sandbox/      /share/dutta/$USER/containers/

sinfo -p dutta -o "%n %C %m"

jid1=$(sbatch \
  --partition=dutta \
  --job-name=pl_stage1 \
  --ntasks=1 --cpus-per-task=2 --mem=4G --gres=gpu:1 --time=06:00:00 \
  --output=logs/stage1_%j.out \
  --export=ALL,IMG=/share/dutta/$USER/containers/pl-pipeline.sif,PATH=/share/apps/singularity/3.7.0/bin:$PATH \
  jobs/stage1.sub | awk '{print $4}')

echo "Stage-1 JobID: $jid1"

# Stage-1 JobID: 8354444

# Sample array ID: 8354445

squeue -u $USER
sacct -j $jid1 -o JobID,State,ExitCode,Elapsed,Reason

#cpu
jid2=$(sbatch \
  --partition=dutta \
  --job-name=pl_sample \
  --dependency=afterok:$jid1 \
  --ntasks=1 --cpus-per-task=2 --mem=8G --gres=gpu:1 --time=06:00:00 \
  --output=logs/sample_%A.out \
  --export=ALL,IMG=/share/dutta/$USER/containers/pl-pipeline.sif,PATH=/share/apps/singularity/3.7.0/bin:$PATH,DEP_JOB_ID=$jid1 \
  jobs/sample_array.sub | awk '{print $4}')

#gpu
jid2=$(sbatch \
  --partition=dutta \
  --job-name=pl_sample \
  --dependency=afterok:$jid1 \
  --ntasks=8 \
  --gres=gpu:1 \
  --cpus-per-task=1 \
  --mem=8G --time=06:00:00 \
  --output=logs/sample_%A_%a.out \
  --export=ALL,IMG=/share/dutta/$USER/containers/pl-pipeline.sif,PATH=/share/apps/singularity/3.7.0/bin:$PATH,DEP_JOB_ID=$jid1 \
  jobs/sample_array.sub | awk '{print $4}')

sacct -j $jid2 -o JobID,State,ExitCode,Elapsed,Reason
tail -f logs/sample_$jid2.out

jid3=$(sbatch \
  --partition=dutta \
  --job-name=pl_aggregate \
  --dependency=afterok:$jid2 \
  --ntasks=1 \
  --cpus-per-task=1 \
  --mem=4G \
  --time=00:30:00 \
  --output=logs/aggregate_%j.out \
  --export=ALL,IMG=/share/dutta/$USER/containers/pl-pipeline.sif,PATH=/share/apps/singularity/3.7.0/bin:$PATH,DEP_JOB_ID=$jid1 \
  jobs/aggregate.sub | awk '{print $4}')
echo "Aggregate JobID: $jid3"

```