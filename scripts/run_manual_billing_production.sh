#!/bin/bash
# Manual Billing Runner for Production (Docker Deployment)
#
# This script triggers the monthly billing mechanism on a production server
# running Odoo in Docker containers (as defined in docker-compose-production.yml).
#
# Usage:
#   ./scripts/run_manual_billing_production.sh [database] [date]
#
# Arguments:
#   database  - Database name (default: postgres)
#   date      - Force date in YYYY-MM-DD format (default: today)
#
# Examples:
#   ./scripts/run_manual_billing_production.sh
#   ./scripts/run_manual_billing_production.sh postgres 2025-11-01
#
# Note: This script must be run from the Odoo project root directory
#       and requires docker-compose to be available.

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
DB_NAME="${1:-postgres}"
FORCE_DATE="${2:-$(date +%Y-%m-%d)}"
CONTAINER_NAME="odoo_app"
COMPOSE_FILE="docker-compose-production.yml"

# Script directory (where this script lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${YELLOW}=== Manual Billing Runner (Production) ===${NC}"
echo "Database: $DB_NAME"
echo "Force Date: $FORCE_DATE"
echo "Container: $CONTAINER_NAME"
echo ""

# Check if scripts directory exists (we're in a Docker-only deployment)
if [ ! -d "$SCRIPT_DIR" ]; then
    echo -e "${RED}Error: Could not locate scripts directory${NC}"
    echo "Script directory: $SCRIPT_DIR"
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: docker-compose or docker is not available${NC}"
    exit 1
fi

# Use docker compose (v2) or docker-compose (v1)
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}Error: Container '$CONTAINER_NAME' is not running${NC}"
    echo "Available containers:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
    exit 1
fi

# Verify Python script exists
if [ ! -f "$SCRIPT_DIR/manual_billing.py" ]; then
    echo -e "${RED}Error: manual_billing.py not found at $SCRIPT_DIR/manual_billing.py${NC}"
    exit 1
fi

echo -e "${YELLOW}Copying Python script to container...${NC}"
# Copy the Python script to the container's /tmp directory
docker cp "$SCRIPT_DIR/manual_billing.py" "$CONTAINER_NAME:/tmp/manual_billing.py"
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to copy script to container${NC}"
    exit 1
fi

echo -e "${YELLOW}Running manual billing in container...${NC}"
echo ""

# Execute the billing script in the container
# Use docker exec to run odoo-bin shell with the script
docker exec -e FORCE_DATE="$FORCE_DATE" "$CONTAINER_NAME" \
    /bin/bash -c "cd /usr/lib/python3/dist-packages/odoo && \
    python3 /usr/bin/odoo shell -c /etc/odoo/odoo.conf -d $DB_NAME --no-http < /tmp/manual_billing.py"

EXIT_CODE=$?

# Clean up: remove the temporary script from container
echo ""
echo -e "${YELLOW}Cleaning up...${NC}"
docker exec "$CONTAINER_NAME" rm -f /tmp/manual_billing.py

# Report results
echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ Manual billing completed successfully${NC}"
    exit 0
else
    echo -e "${RED}✗ Manual billing failed with exit code $EXIT_CODE${NC}"
    exit $EXIT_CODE
fi
