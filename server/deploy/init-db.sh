#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE cottage_monitoring;
    CREATE DATABASE cottage_monitoring_dev;
    \c cottage_monitoring
    CREATE EXTENSION IF NOT EXISTS timescaledb;
    \c cottage_monitoring_dev
    CREATE EXTENSION IF NOT EXISTS timescaledb;
EOSQL
