# Kill Stuff
kill -9 $(lsof -t -i:3000)
kill -9 $(lsof -t -i:3001)
kill -9 $(lsof -t -i:8000)
kill -9 $(lsof -t -i:6000)

# Start the vector database
docker compose -f examples/deploy/docker-compose.milvus.yml up -d
docker compose -f examples/deploy/docker-compose.milvus.yml logs --follow

# Run Ingestion:
cd examples/pynemo_dataprep/scripts
bash bootstrap_milvus.sh
./bootstrap_milvus.sh ../../pynemo_dataprep

# Set up code exector:
./src/nat/tool/code_execution/local_sandbox/start_local_sandbox.sh local-sandbox examples/pynemo_dataprep

# Open UI:
cd external/nat-ui
npm ci
npm run dev

# Serve:
nat serve --config_file=examples/pynemo_dataprep/configs/config.yaml

# Other:
uv pip install -e .
uv pip install -e '.[langchain]'
uv pip install -e examples/RAG/simple_rag


nat run --config_file=examples/pynemo_dataprep/configs/config.yaml --input "who was Djikstra?"
nat run --config_file=examples/pynemo_dataprep/configs/config.yaml --input "what is 4+4"
nat run --config_file=examples/pynemo_dataprep/configs/config.yaml --input "What model architectures for External Aerodynamics CFD Surrogates are supported in PhysicsNemo"
nat run --config_file=examples/pynemo_dataprep/configs/config.yaml --input "What model architectures for External Aerodynamics CFD Surrogates are supported in PhysicsNemo Repository"
nat run --config_file=examples/pynemo_dataprep/configs/config.yaml --input "Can you explain the model XAeroNet: Scalable Neural Models for External Aerodynamics presented in the PhysicsNemo"
nat run --config_file=examples/pynemo_dataprep/configs/config.yaml --input "Can you explain the model XAeroNet: Scalable Neural Models for External Aerodynamics presented in the PhysicsNemo"


# RAG:

python langchain_web_ingest.py \
  --start_url https://docs.nvidia.com/physicsnemo/latest/physicsnemo/examples/cfd/vortex_shedding_mgn/README.html \
  --base_url https://docs.nvidia.com/physicsnemo/latest/physicsnemo/examples/cfd/ \

nat run --config_file=examples/pynemo_dataprep/configs/config.yaml --input "Write code to train the DoMINO model on the DrivAerML example"
nat run --config_file=examples/pynemo_dataprep/configs/config.yaml --input "Can you explain the model XAeroNet: Scalable Neural Models for External Aerodynamics presented in the PhysicsNemo"
nat run --config_file=examples/pynemo_dataprep/configs/config.yaml --input "How can I train a model on the DrivAer Dataset using the PhysicsNemo Library"
nat run --config_file=examples/pynemo_dataprep/configs/config.yaml --input "What is the exact code behind the DoMINO model in PhysicsNemo Repository"
nat run --config_file=examples/pynemo_dataprep/configs/config.yaml --input "Write a function to create a DGL Graph and count the number of nodes. Test it on a dummy graph you create."

# Evaluation System

An automated evaluation system is available in the `evals/` directory:

```bash
# Run all evaluation questions
./examples/pynemo_dataprep/evals/run_eval.sh

# View summary of results
./examples/pynemo_dataprep/evals/summarize_results.sh

# Check individual results
cat evals/results/question_1.txt
```

See `evals/README.md` for full documentation of the evaluation system.

Questions for evaluation are stored in `evals/questions.txt`.