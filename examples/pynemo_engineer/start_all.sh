#!/bin/bash

# PhysicsNemo Engineer Agent - Complete Startup Script
# This script starts all necessary components for the PhysicsNemo Engineer Agent
#
# Usage:
#   ./start_all.sh              # Start services only (no NAT server)
#   ./start_all.sh --serve      # Start services and NAT server

set -e  # Exit on error

# Parse command line arguments
SERVE_NAT=false
for arg in "$@"; do
    case $arg in
        --serve)
            SERVE_NAT=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --serve     Start NAT server after services (default: disabled)"
            echo "  --help      Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the repository root directory (assuming this script is in examples/pynemo_engineer/)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}PhysicsNemo Engineer Agent Startup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Array to track background process PIDs for cleanup
declare -a BG_PIDS=()
declare -a DOCKER_SERVICES=()
CLEANUP_ON_EXIT=true

# Cleanup function
cleanup() {
    # Only cleanup if requested (on Ctrl+C or error, not normal exit)
    if [ "$CLEANUP_ON_EXIT" = true ]; then
        echo -e "\n${YELLOW}Shutting down all services...${NC}"
        
        # Kill background processes
        for pid in "${BG_PIDS[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "${YELLOW}Stopping process $pid${NC}"
                kill -TERM "$pid" 2>/dev/null || true
            fi
        done
        
        # Stop Docker services
        if [ ${#DOCKER_SERVICES[@]} -gt 0 ]; then
            for service in "${DOCKER_SERVICES[@]}"; do
                if [ "$service" = "milvus" ]; then
                    echo -e "${YELLOW}Stopping Milvus...${NC}"
                    docker compose -f examples/deploy/docker-compose.milvus.yml down 2>/dev/null || true
                elif [ "$service" = "sandbox" ]; then
                    echo -e "${YELLOW}Stopping sandbox container...${NC}"
                    docker stop local-sandbox 2>/dev/null || true
                    docker rm local-sandbox 2>/dev/null || true
                fi
            done
        fi
        
        echo -e "${GREEN}Cleanup complete${NC}"
    fi
    exit 0
}

# Register cleanup function for interrupts and errors only
trap cleanup INT TERM

# Step 1: Kill any existing processes on required ports
echo -e "${YELLOW}[1/4] Cleaning up existing processes on ports 3000, 3001, 8000, 6000...${NC}"
for port in 3000 3001 8000 6000; do
    pid=$(lsof -t -i:$port 2>/dev/null || true)
    if [ ! -z "$pid" ]; then
        echo -e "${YELLOW}  Killing process $pid on port $port${NC}"
        kill -9 $pid 2>/dev/null || true
    fi
done
echo -e "${GREEN}✓ Port cleanup complete${NC}\n"
sleep 2

# Step 2: Start Vector Database (Milvus)
echo -e "${YELLOW}[2/4] Starting Vector Database (Milvus)...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed or not in PATH${NC}"
    exit 1
fi

docker compose -f examples/deploy/docker-compose.milvus.yml up -d
DOCKER_SERVICES+=("milvus")
echo -e "${GREEN}✓ Milvus Docker containers started${NC}"

# Wait for Milvus to be ready with health check
echo -e "${BLUE}  Waiting for Milvus to be ready...${NC}"
MAX_WAIT=120  # Maximum 2 minutes
MIN_WAIT=30   # Minimum wait time even if port appears ready
ELAPSED=0
MILVUS_READY=false
PORT_AVAILABLE=false

# Enforce minimum wait time first
echo -e "${BLUE}  Waiting minimum initialization time...${NC}"
while [ $ELAPSED -lt $MIN_WAIT ]; do
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    if [ $((ELAPSED % 10)) -eq 0 ]; then
        echo -e "${BLUE}  Initializing... (${ELAPSED}s/${MIN_WAIT}s minimum)${NC}"
    fi
done

echo -e "${BLUE}  Checking Milvus availability...${NC}"

# Now check if Milvus is actually responding
while [ $ELAPSED -lt $MAX_WAIT ]; do
    # Try to connect to Milvus using Python
    if python3 -c "
from pymilvus import connections
try:
    connections.connect('default', host='localhost', port='19530', timeout=5)
    connections.disconnect('default')
    exit(0)
except Exception:
    exit(1)
" 2>/dev/null; then
        MILVUS_READY=true
        echo -e "${GREEN}✓ Milvus is ready and accepting connections (took ~${ELAPSED}s)${NC}"
        break
    fi
    
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    if [ $((ELAPSED % 10)) -eq 0 ]; then
        echo -e "${BLUE}  Still waiting for Milvus to respond... (${ELAPSED}s/${MAX_WAIT}s)${NC}"
    fi
done

if [ "$MILVUS_READY" = false ]; then
    echo -e "${RED}Error: Milvus failed to start within ${MAX_WAIT} seconds${NC}"
    echo -e "${YELLOW}Displaying recent Milvus logs:${NC}"
    echo "---"
    docker compose -f examples/deploy/docker-compose.milvus.yml logs --tail=50 milvus-standalone 2>/dev/null || echo "Could not retrieve logs"
    echo "---"
    echo -e "${YELLOW}Tip: Check full logs with: docker compose -f examples/deploy/docker-compose.milvus.yml logs${NC}"
    exit 1
fi
echo ""

# Step 3: Start Code Executor (Local Sandbox)
echo -e "${YELLOW}[3/4] Starting Code Executor (Local Sandbox)...${NC}"

SANDBOX_NAME="local-sandbox"
SANDBOX_DOCKERFILE="$REPO_ROOT/src/nat/tool/code_execution/local_sandbox/Dockerfile.sandbox"
OUTPUT_DATA_PATH="$REPO_ROOT/examples/pynemo_engineer"
DOCKER_COMMAND=${DOCKER_COMMAND:-"docker"}

# Check if Docker image exists, build if needed
if ! ${DOCKER_COMMAND} images ${SANDBOX_NAME} | grep -q "${SANDBOX_NAME}"; then
    echo -e "${BLUE}  Building sandbox Docker image...${NC}"
    cd "$REPO_ROOT"
    ${DOCKER_COMMAND} build --tag=${SANDBOX_NAME} \
        --build-arg="UWSGI_PROCESSES=10" \
        --build-arg="UWSGI_CHEAPER=5" \
        -f "$SANDBOX_DOCKERFILE" . > /tmp/pynemo_sandbox_build.log 2>&1
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to build sandbox image${NC}"
        echo -e "${YELLOW}Check log: /tmp/pynemo_sandbox_build.log${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Sandbox image built${NC}"
else
    echo -e "${BLUE}  Using existing sandbox Docker image${NC}"
fi

# Stop any existing sandbox container
${DOCKER_COMMAND} stop ${SANDBOX_NAME} 2>/dev/null || true
${DOCKER_COMMAND} rm ${SANDBOX_NAME} 2>/dev/null || true

# Start sandbox container in detached mode
echo -e "${BLUE}  Starting sandbox container...${NC}"
${DOCKER_COMMAND} run -d --name=${SANDBOX_NAME} \
  -p 6000:6000 \
  -v "${OUTPUT_DATA_PATH}:/workspace" \
  ${SANDBOX_NAME} > /tmp/pynemo_sandbox_id.txt 2>&1

if [ $? -eq 0 ]; then
    SANDBOX_CONTAINER_ID=$(cat /tmp/pynemo_sandbox_id.txt)
    echo -e "${GREEN}✓ Code Executor started (Container: ${SANDBOX_CONTAINER_ID:0:12})${NC}"
    echo -e "${BLUE}  Container name: ${SANDBOX_NAME}${NC}"
    echo -e "${BLUE}  Port: 6000${NC}"
    echo -e "${BLUE}  Logs: docker logs ${SANDBOX_NAME}${NC}"
    # Track for cleanup
    DOCKER_SERVICES+=("sandbox")
else
    echo -e "${RED}Error: Failed to start sandbox container${NC}"
    echo -e "${YELLOW}Check: docker logs ${SANDBOX_NAME}${NC}"
    exit 1
fi
sleep 2
echo ""

# Step 4: Start UI (nat-ui)
echo -e "${YELLOW}[4/4] Starting UI (nat-ui)...${NC}"
UI_DIR="$REPO_ROOT/external/nat-ui"

if [ ! -d "$UI_DIR" ]; then
    echo -e "${RED}Error: UI directory not found at $UI_DIR${NC}"
    exit 1
fi

cd "$UI_DIR"

# Check if node_modules exists, if not run npm ci
if [ ! -d "node_modules" ]; then
    echo -e "${BLUE}  Installing UI dependencies...${NC}"
    npm ci
fi

# Start UI in background
npm run dev > /tmp/pynemo_ui.log 2>&1 &
UI_PID=$!
BG_PIDS+=($UI_PID)
cd "$REPO_ROOT"

# Wait briefly to ensure it started
sleep 2

# Verify the UI is still running
if kill -0 $UI_PID 2>/dev/null; then
    echo -e "${GREEN}✓ UI started (PID: $UI_PID)${NC}"
    echo -e "${BLUE}  Log: /tmp/pynemo_ui.log${NC}"
    echo -e "${BLUE}  Waiting for UI to initialize (15 seconds)...${NC}"
    sleep 13  # Total 15 seconds (2 + 13)
else
    echo -e "${RED}Error: UI failed to start${NC}"
    echo -e "${YELLOW}Check log: /tmp/pynemo_ui.log${NC}"
    exit 1
fi
echo ""

# Step 5: Optionally Start NAT Server
if [ "$SERVE_NAT" = true ]; then
    echo -e "${YELLOW}[5/5 OPTIONAL] Starting NAT Server...${NC}"
    CONFIG_FILE="$REPO_ROOT/examples/pynemo_engineer/configs/config.yaml"

    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${RED}Error: Config file not found at $CONFIG_FILE${NC}"
        exit 1
    fi

    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}All services started successfully!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}Service Status:${NC}"
    echo -e "  • Milvus (Vector DB):  ${GREEN}Running${NC} (Docker)"
    echo -e "  • Code Executor:       ${GREEN}Running${NC} (Container: local-sandbox, Port: 6000)"
    echo -e "  • UI:                  ${GREEN}Running${NC} (PID: $UI_PID, Log: /tmp/pynemo_ui.log)"
    echo -e "  • UI URL:              ${BLUE}http://localhost:3000${NC}"
    echo -e "  • NAT Server:          ${YELLOW}Starting...${NC}"
    echo ""
    echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
    echo -e "${GREEN}========================================${NC}\n"

    # Start the NAT server in foreground (this blocks until interrupted)
    nat serve --config_file="$CONFIG_FILE"
else
    echo -e "${YELLOW}[5/5 OPTIONAL] NAT Server startup skipped (use --serve to enable)${NC}"
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}All services started successfully!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${BLUE}Service Status:${NC}"
    echo -e "  • Milvus (Vector DB):  ${GREEN}Running${NC} (Docker)"
    echo -e "  • Code Executor:       ${GREEN}Running${NC} (Container: local-sandbox, Port: 6000)"
    echo -e "  • UI:                  ${GREEN}Running${NC} (PID: $UI_PID, Log: /tmp/pynemo_ui.log)"
    echo -e "  • UI URL:              ${BLUE}http://localhost:3000${NC}"
    echo -e "  • NAT Server:          ${YELLOW}Not started${NC}"
    echo ""
    echo -e "${BLUE}To start the NAT server manually, run:${NC}"
    echo -e "  ${GREEN}nat serve --config_file=examples/pynemo_engineer/configs/config.yaml${NC}"
    echo ""
    echo -e "${BLUE}Or restart this script with --serve flag:${NC}"
    echo -e "  ${GREEN}./examples/pynemo_engineer/start_all.sh --serve${NC}"
    echo ""
    echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
    echo -e "${GREEN}========================================${NC}\n"
    
    # Disable cleanup on normal exit - services should persist
    CLEANUP_ON_EXIT=false
    
    # Keep the script running so services stay up
    echo -e "${BLUE}Services are running in the background. Monitoring...${NC}"
    echo -e "${BLUE}View logs with:${NC}"
    echo -e "  • Code Executor: docker logs local-sandbox"
    echo -e "  • UI: tail -f /tmp/pynemo_ui.log"
    echo -e "  • Milvus: docker compose -f examples/deploy/docker-compose.milvus.yml logs"
    echo ""
    
    # Disown the background processes so they survive script exit
    for pid in "${BG_PIDS[@]}"; do
        disown $pid 2>/dev/null || true
    done
    
    echo -e "${BLUE}Services will continue running in the background.${NC}"
    echo -e "${BLUE}To stop them, run:${NC}"
    echo -e "  ${GREEN}./examples/pynemo_engineer/stop_all.sh${NC}"
    echo -e "${BLUE}Or stop services manually:${NC}"
    echo -e "  kill $UI_PID"
    echo -e "  docker stop local-sandbox && docker rm local-sandbox"
    echo -e "  docker compose -f examples/deploy/docker-compose.milvus.yml down"
    echo ""
fi

