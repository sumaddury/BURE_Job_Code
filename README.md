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

fairseq installation

```bash
# ── 1. clone & init submodules ─────────────────────────────────────────
git clone https://github.com/<your-fork>/fairseq2.git fairseq2_repo
cd fairseq2_repo
git submodule update --init --recursive

# ── 2. one-time system tools (Homebrew) ────────────────────────────────
brew install python@3.12 libsndfile cmake ninja     # skip if already present

# ── 3. Python-3.12 virtual-env with core wheels ────────────────────────
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip numpy
pip install torch==2.7.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r native/python/requirements-build.txt    # cmake/ninja/pybind11

# ── 4. build & install the C++ backend (fairseq2n) ─────────────────────
cd native
cmake -GNinja -B build -DPython3_EXECUTABLE="$(which python)" -DCMAKE_BUILD_TYPE=Release
cmake --build build
cd python && pip install -e . && cd ../../            # installs fairseq2n 0.5.0.dev0

# ── 5. install the Python layer + all test extras ──────────────────────
pip install -e ".[arrow]"          # pulls pyarrow, polars, retrying, xxhash
pip install -r requirements-devel.txt   # pytest, mypy, etc.

# ── 6. run the full CPU test-suite ─────────────────────────────────────
pytest -q                           # expect: 901 passed, 12 skipped
```

commands:
```bash

rm -rf pyro_repo
mkdir -p ast_dir
python3 AssertSpecFinder.py compile --project-link https://github.com/pyro-ppl/pyro.git \
    --clone-dir pyro_repo \
    --asts-out ast_dir/pyro_asts.pkl

mkdir -p test_csvs
python3 AssertSpecFinder.py mine --asts-in ast_dir/pyro_asts.pkl \
    --test-dir tests \
    --csv-target test_csvs/pyro_assertions.csv \
    --funcs-out ast_dir/pyro_funcs.pkl

deactivate
rm -rf .venv
python3.10 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r pyro_custom_cpu.txt

# cd lightning_repo
# make test
# cd ..

pip freeze | grep -vE '^\s*-e\b' > constraints.txt
pip install -r script_reqs.txt \
    --constraint constraints.txt

python3 Seeder.py remove_seed --asts-in ast_dir/pyro_asts.pkl

python3 Instrumentor.py log --csv-in test_csvs/pyro_assertions.csv \
    --csv-out test_csvs/pyro_assertions_m1.csv \
    --asts-in ast_dir/pyro_asts.pkl \
    --funcs-in ast_dir/pyro_funcs.pkl

cp conftest.py pyro_repo/

# rm -rf lightning_dists
mkdir -p pyro_dists

python3 Distributions.py sample_csv --csv-in test_csvs/pyro_assertions_m1.csv \
    --trials 8 \
    --workers 4 \
    --dir-out temp_dists \
    --assertions "$(paste -sd, pyro_interest_gpu.txt)" \
    --repo-name pyro_repo \
    --seed-value 42 \
    --seed-config-file-in ../seed_configs.yaml \
    --seed-config-names "NO_SEEDS;RANDOM,NUMPY,TORCH"
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
sinfo -N -p dutta -o "%n %G"

nlplarge-compute-01
#cpu
jid1=$(sbatch \
  --partition=dutta \
  --account=dutta \
  --job-name=pl_stage1 \
  --ntasks=1 --cpus-per-task=2 --mem=4G --time=01:00:00 \
  --output=logs/stage1_%j.out \
  --export=ALL,IMG=/share/dutta/$USER/containers/pl-pipeline.sif,PATH=/share/apps/singularity/3.7.0/bin:$PATH \
  jobs/stage1.sub | awk '{print $4}')

#gpu

jid1=$(sbatch \
  --gres=gpu:h100:1 \
  --partition=dutta \
  --account=dutta \
  --ntasks=1 --cpus-per-task=2 --mem=8G --time=01:00:00 \
  --job-name=pl_stage1 \
  --output=logs/stage1_%j.out \
  --export=ALL,IMG=/share/dutta/$USER/containers/pl-pipeline.sif,PATH=/share/apps/singularity/3.7.0/bin:$PATH \
  jobs/stage1.sub | awk '{print $4}')

jid1=$(sbatch \
  --gres=gpu:a6000:1 \
  --nodelist=zabih-compute-01 \
  --partition=gpu \
  --account=dutta \
  --ntasks=1 --cpus-per-task=2 --mem=8G --time=01:00:00 \
  --job-name=pl_stage1 \
  --output=logs/stage1_%j.out \
  --export=ALL,IMG=/share/dutta/$USER/containers/pl-pipeline.sif,PATH=/share/apps/singularity/3.7.0/bin:$PATH \
  jobs/stage1.sub | awk '{print $4}')

node=$(sacct -j "$jid1" -n -P -o NodeList | head -1)
part=$(sacct -j "$jid1" -n -P -o Partition | head -1)

srun --partition=gpu --nodelist=zabih-compute-01 --account=dutta \
     --gres=gpu:0 --cpus-per-task=2 --time=01:00:00 --mem=8G --pty \
     /share/apps/singularity/3.7.0/bin/singularity exec --nv \
     --bind /scratch:/scratch \
     /share/dutta/$USER/containers/pl-pipeline.sif bash

srun --partition=dutta --account=dutta \
     --cpus-per-task=2 --time=01:00:00 --mem=8G --pty \
     /share/apps/singularity/3.7.0/bin/singularity exec --nv \
     --bind /scratch:/scratch \
     /share/dutta/$USER/containers/pl-pipeline.sif bash

echo "Stage-1 JobID: $jid1"

squeue -u $USER
sacct -j $jid1 -o JobID,State,ExitCode,Elapsed,Reason

#cpu
jid2=$(sbatch \
  --partition=dutta \
  --account=dutta \
  --job-name=pl_sample \
  --dependency=afterok:$jid1 \
  --ntasks=1 --cpus-per-task=32 --mem=24G --gres=gpu:0 --time=48:00:00 \
  --output=logs/sample_%A.out \
  --export=ALL,IMG=/share/dutta/$USER/containers/pl-pipeline.sif,PATH=/share/apps/singularity/3.7.0/bin:$PATH,OUTDIR=pyro_dists,DEP_JOB_ID=$jid1 \
  jobs/sample_array.sub | awk '{print $4}')


# Past cpu job ids (dutta):
# stage1: 8402430
# sample: 8402471
#gpu

# Start: ~12 AM FRI JUL 11

# Current gpu job ids (zabih-compute-01)
# stage1: 8403615
# 1: 8403618
# 2: 8403621

# Current gpu job ids (dutta)
# stage1: 8403623
# 1: 8403633

# Start: 2 PM FRI JUL 11

# Current multi-thread job ids (dutta)
# stage1: 8406181
# 1: 8406186

jid2=$(sbatch \
  --account=dutta \
  --partition=dutta \
  --job-name=pl_sample \
  --dependency=afterok:$jid1 \
  --ntasks=1 \
  --cpus-per-task=8 \
  --mem=48G \
  --gres=gpu:h100:1 \
  --time=48:00:00 \
  --output=logs/sample_%A.out \
  --export=ALL,IMG=/share/dutta/$USER/containers/pl-pipeline.sif,PATH=/share/apps/singularity/3.7.0/bin:$PATH,DEP_JOB_ID=$jid1,OUTDIR=pyro_dists_3 \
  jobs/sample_array.sub | awk '{print $4}')

jid2=$(sbatch \
  --account=dutta \
  --partition=gpu \
  --nodelist=zabih-compute-01 \
  --job-name=pl_sample \
  --dependency=afterok:$jid1 \
  --ntasks=1 \
  --cpus-per-task=4 \
  --mem=24G \
  --gres=gpu:a6000:1 \
  --time=48:00:00 \
  --output=logs/sample_%A.out \
  --export=ALL,IMG=/share/dutta/$USER/containers/pl-pipeline.sif,PATH=/share/apps/singularity/3.7.0/bin:$PATH,DEP_JOB_ID=$jid1,OUTDIR=pyro_dists_2 \
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