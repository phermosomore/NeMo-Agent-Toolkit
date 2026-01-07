#!/bin/bash

# PhysicsNemo Engineer Agent - Stop All Services Script

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the repository root directory
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Stopping PhysicsNemo Engineer Services${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Stop processes on ports
echo -e "${YELLOW}Stopping processes on ports...${NC}"
for port in 3000 3001 8000 6000; do
    pid=$(lsof -t -i:$port 2>/dev/null || true)
    if [ ! -z "$pid" ]; then
        echo -e "  ${YELLOW}Killing process $pid on port $port${NC}"
        kill -TERM $pid 2>/dev/null || kill -9 $pid 2>/dev/null || true
        sleep 1
    else
        echo -e "  ${GREEN}Port $port is already free${NC}"
    fi
done
echo ""

# Stop sandbox container
echo -e "${YELLOW}Stopping sandbox container...${NC}"
if docker ps --filter "name=local-sandbox" --format "{{.Names}}" 2>/dev/null | grep -q "local-sandbox"; then
    docker stop local-sandbox 2>/dev/null || true
    docker rm local-sandbox 2>/dev/null || true
    echo -e "${GREEN}✓ Sandbox container stopped${NC}"
else
    echo -e "${GREEN}✓ Sandbox container not running${NC}"
fi
echo ""

# Stop Milvus services
echo -e "${YELLOW}Stopping Milvus services...${NC}"
if docker compose -f examples/deploy/docker-compose.milvus.yml ps --services 2>/dev/null | grep -q .; then
    docker compose -f examples/deploy/docker-compose.milvus.yml down
    echo -e "${GREEN}✓ Milvus services stopped${NC}"
else
    echo -e "${GREEN}✓ Milvus services not running${NC}"
fi
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}All services stopped${NC}"
echo -e "${GREEN}========================================${NC}"

