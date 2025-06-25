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

G2 commands:
```bash
ssh sm2939@g2-login-01.coecis.cornell.edu
module load singularity/3.7


git clone git@github.com:sumaddury/BURE_Job_Code.git
cd BURE_Job_Code

singularity build --fakeroot pl_pipeline.sif containers/Dockerfile

mkdir -p /share/$USER/containers
mv pl_pipeline.sif /share/$USER/containers/

jid1=$(sbatch \
  --job-name=pl_stage1 \
  --cpus-per-task=1 --ntasks=4 --mem=8G --time=06:00:00 \
  --gres=gpu:0 \
  --export=ALL,IMG=/share/$USER/containers/pl_pipeline.sif \
  jobs/stage1.sub | awk '{print $4}')s

sbatch \
  --job-name=pl_sample \
  --dependency=afterok:$jid1 \
  --cpus-per-task=1 --ntasks=4 --mem=8G --time=06:00:00 \
  --gres=gpu:0 \
  --export=ALL,IMG=/share/$USER/containers/pl_pipeline.sif,DEP_JOB_ID=$jid1 \
  jobs/sample_array.sub
```