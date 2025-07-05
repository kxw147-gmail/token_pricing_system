Token Pricing System

The Token Pricing System is a robust FastAPI application engineered to efficiently fetch, store, aggregate, and serve real-time and historical cryptocurrency token prices. This initial implementation is optimized for fast development with self-contained, single-host deployment, featuring secure API endpoints, autonomous background services for data ingestion and aggregation, integrated in-memory caching, persistent data storage, and extensive logging capabilities. For details on achieving a more decoupled, distributed, and highly scalable system architecture, please refer to the 'Future Enhancements' section below.


🚀 Features
Real-time Price Ingestion: Fetches 5-minute granularity price data for specified cryptocurrencies from CoinGecko.

Historical Data Storage: Persists raw 5-minute and aggregated hourly/daily price data in a local SQLite database (easily configurable for PostgreSQL/MySQL).

Data Aggregation: Automatically aggregates 5-minute data into hourly and daily candles.

Data Retention: Configurable job to periodically clean up old raw data.

Secure API: User registration, login, and JWT-based authentication for all data access endpoints.

Rate Limiting: Protects API endpoints against abuse by limiting requests per user.

In-Memory Caching: Speeds up responses for frequently accessed latest price data.

Comprehensive Logging: Detailed logging to console and file for monitoring, debugging, and operational insights.

Testing Suite: Includes unit, integration, and end-to-end tests for reliability.

🛠️ Technology Stack
Framework: FastAPI

Database: SQLAlchemy (ORM) with SQLite (default)

Asynchronous HTTP Client: httpx

Authentication: python-jose (JWT), passlib (bcrypt)

Retries & Rate Limiting: tenacity, asyncio_rate_limit

Environment Management: python-dotenv

Testing: pytest, pytest-asyncio, pytest-mock

📂 Project Structure
token_pricing_system/
├── app/
│   ├── api/                  # API Endpoints and Security
│   │   ├── endpoints.py      # Main API routes (prices, auth)
│   │   └── security.py       # JWT token handling and user authentication
│   ├── core/                 # Core utilities and configuration
│   │   ├── config.py         # Application settings
│   │   ├── db.py             # Database engine and session management
│   │   ├── logging_config.py # Logging setup
│   │   └── security_utils.py # Password hashing and JWT creation
│   ├── crud/                 # CRUD operations for database interaction
│   │   └── token_price.py
│   ├── models/               # SQLAlchemy models (database schemas)
│   │   ├── token_price.py
│   │   └── user.py
│   ├── schemas/              # Pydantic schemas (data validation/serialization)
│   │   ├── token_price.py
│   │   └── user.py
│   ├── services/             # Business logic and background tasks
│   │   ├── aggregation_service.py # Hourly/Daily aggregation, data retention
│   │   ├── ingestion_service.py   # CoinGecko price fetching and raw data storage
│   │   └── cache_service.py       # In-memory caching
│   ├── middlewares/          # FastAPI middleware
│   │   └── rate_limit.py     # User-specific API rate limiting
│   └── main.py               # Main FastAPI application instance
├── scripts/                  # Utility scripts
│   └── setup_db.py           # Database table creation script
├── tests/                    # Project tests
│   ├── conftest.py           # Pytest fixtures and test setup
│   ├── unit/
│   │   └── test_services.py  # Unit tests for service modules
│   ├── integration/
│   │   └── test_api.py       # Integration tests for API endpoints
│   └── e2e/
│       └── test_full_flow.py # End-to-end test simulating full user flow
├── client/                   # Example client-side usage and test
│   └── client_example.py     # Example Python client script
├── .env                      # Environment variables
├── requirements.txt          # Python dependencies
├── README.md                 # Project documentation
├── local_prices.db           # Default SQLite database file (created on setup)
├── app.log                   # Default application log file (created on run)


🚀 Getting Started
Follow these steps to set up and run the Token Pricing System locally.

1. Prerequisites
Python 3.11+

pip (Python package installer)

Bash
brew install python@3.11.5
python --version

2. Clone the Repository
Bash

git clone https://github.com/your-username/token-pricing-system.git # Replace with your repo URL
cd token-pricing-system

3. Create and Activate a Virtual Environment
It's highly recommended to use a virtual environment to manage dependencies.

Bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows, use `venv\Scripts\activate`

4. Install Dependencies
Bash
pip install -r requirements.txt

5. Configure Environment Variables
Modify .env file in the project root and fill in the values.

# .env file
DATABASE_URL="sqlite:///./local_prices.db" # Local SQLite file database
COINGECKO_API_KEY="YOUR_COINGECKO_API_KEY" # Get a free API key for CoinGecko free tier, needed for higher limits
JWT_SECRET_KEY="super-secret-jwt-key-replace-me-with-a-strong-one" # Replace with a strong, random string, Bash: "openssl rand -hex 32"
JWT_ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=60
RATE_LIMIT_PER_MINUTE=60
DATA_RETENTION_RAW_DAYS=30 # Retain raw 5min data for 30 days in DB
DATA_RETENTION_AGG_DAYS=365 * 5 # Retain aggregated 1h/1d data for 5 years in DB
LOG_LEVEL="INFO" # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE_PATH="app.log" # Path to the log file (relative to project root)

Important: Replace YOUR_COINGECKO_API_KEY with your actual CoinGecko API key if you have one (or plan to use a paid tier for higher rate limits). The system works without it for the free tier, but explicit key usage might be required for higher throughput. Also, generate a strong, random string for JWT_SECRET_KEY using command

Bash
openssl rand -hex 32

6. Initialize the Database
Run the setup script to create the necessary database tables:

Bash
python scripts/setup_db.py
This will create local_prices.db in your project root.

▶️ Running the Application
After completing the setup, you can start the FastAPI application:

Bash

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
The --reload flag is great for development as it automatically reloads the server on code changes. For production, remove this flag.

The application will be accessible at http://127.0.0.1:8000.

📄 API Documentation
Once the server is running, you can access the interactive API documentation (Swagger UI) at:

Swagger UI: http://127.0.0.1:8000/docs

ReDoc: http://127.0.0.1:8000/redoc

Use these interfaces to explore the available endpoints, register users, log in, and test the price queries.

📊 Key Endpoints
POST /api/v1/register: Register a new user.

POST /api/v1/token: Log in and obtain an access token.

GET /api/v1/users/me/: Get current user's details (requires authentication).

GET /api/v1/prices/{token_symbol}?granularity={granularity}&start_time={start_time}&end_time={end_time}: Get historical prices for a token (requires authentication).

GET /api/v1/prices/latest/{token_symbol}?granularity={granularity}: Get the latest price for a token (requires authentication, uses cache).

POST /api/v1/prices/prefetch/{token_symbol}: Manually trigger immediate ingestion for a token (requires authentication).

🏃 Background Services
The app.main.py starts the following background tasks on application startup:

Ingestion Loop: Continuously fetches 5-minute price data for configured symbols (default: bitcoin, ethereum, ripple, solana, cardano, dogecoin) every 5 minutes.

Aggregation Loop: Runs hourly and daily aggregations of raw 5-minute data. Hourly aggregates run every hour, and daily aggregates run once a day around midnight UTC.

Data Retention Job: Periodically prunes old 5-minute granularity data based on the DATA_RETENTION_RAW_DAYS setting in .env.

You'll see logs from these services appearing in your console and app.log.

🪵 Logging
The application uses Python's built-in logging module.

Logs are printed to the console.

Logs are also written to the file specified by LOG_FILE_PATH in your .env (default: app.log).

You can adjust the verbosity of the logs by changing the LOG_LEVEL environment variable (DEBUG, INFO, WARNING, ERROR, CRITICAL).

🧪 Running Tests
The project includes a comprehensive test suite.

Bash

# Run all tests
pytest

# Run unit tests only
pytest tests/unit/

# Run integration tests only
pytest tests/integration/

# Run end-to-end tests only
pytest tests/e2e/
Tests use an in-memory SQLite database to ensure isolation and speed.

🎯 Client Example
A basic Python client example is provided to demonstrate how to interact with the API:

Bash

# First, ensure your FastAPI server is running in another terminal
python client/client_example.py
You'll need to open client/client_example.py and potentially adjust the API_BASE_URL if your server is running on a different address/port. This example will guide you through user registration, login, and fetching token prices.



🐳 Future Enhancements
While this system currently provides a robust single-host solution, here are key areas for future architectural improvements to achieve greater decoupling, responsibility separation, and horizontal scalability required for production-grade, high-traffic scenarios:

🚀 Architectural Scaling & Decoupling
Dedicated Data Cache:

Problem: The current in-memory cache is local to the application instance, meaning cached data is lost on restarts and not shared across multiple running instances.

Solution: Integrate a distributed, persistent cache like Redis or Memcached. This would provide a shared cache layer across multiple API instances, improve cache hit rates, offer better performance, and ensure cache data persistence independent of the application server's lifecycle.

Non-InMemory & Scalable Database:

Problem: The current SQLite database is excellent for local development but unsuitable for high-concurrency, large-scale, or distributed environments.

Solution: Transition to a robust and scalable relational database (e.g., PostgreSQL, MySQL) for transactional data, or consider a specialized Time-Series Database (e.g., InfluxDB, TimescaleDB for PostgreSQL) which is highly optimized for handling vast volumes of time-stamped price data efficiently. This would enable better performance under load, higher data integrity, and easier scaling.

Distributed Architecture / Microservices:

Problem: The current setup is a monolithic application with ingestion, aggregation, and API serving running within the same process. This limits independent scaling and introduces tightly coupled responsibilities.

Solution: Decouple the core functionalities into distinct microservices (e.g., an Ingestion Service, an Aggregation Service, an API Gateway/Query Service).

Asynchronous Communication: Introduce a message broker (e.g., Kafka, RabbitMQ, AWS SQS/SNS) to facilitate asynchronous, fault-tolerant communication between these services. For example, the Ingestion Service publishes new prices to a topic, and the Aggregation Service consumes from it.

📦 Deployment & Operations
Containerization & Orchestration (🐳 Docker & Kubernetes):

Problem: Manual deployment can be complex, and environment consistency across development, staging, and production can be challenging.

Solution:

Docker: Create Dockerfiles for each microservice (if decoupled) or the monolithic application to package them into isolated, portable containers.

Docker Compose: Use docker-compose.yml for local multi-service development and testing setup.

Kubernetes: For production, deploy and manage containers using Kubernetes. This will provide automated scaling, load balancing, service discovery, self-healing capabilities, and simplified updates.

Continuous Integration/Continuous Deployment (CI/CD) Pipeline:

Problem: Manual testing and deployment are error-prone and slow.

Solution: Implement a CI/CD pipeline (e.g., using GitHub Actions, GitLab CI/CD, Jenkins, ArgoCD) to automate the entire software delivery process, from code commit through testing and deployment to production.

Monitoring, Logging, & Alerting:

Problem: While basic logging is in place, comprehensive observability is crucial for production systems.

Solution:

Metrics: Integrate with a metrics collection system like Prometheus for capturing application and infrastructure metrics.

Visualization: Use Grafana to visualize these metrics and create dashboards for system health.

Centralized Logging: Implement a centralized logging solution (e.g., ELK Stack - Elasticsearch, Logstash, Kibana, or Grafana Loki) for aggregating logs from all services.

Alerting: Configure alerts (e.g., via PagerDuty, Slack, email) for critical events, performance bottlenecks, or service failures.

API Gateway & Load Balancing:

Problem: Direct exposure of services can be less secure and harder to manage traffic for.

Solution: Deploy an API Gateway (e.g., Nginx, Kong, AWS API Gateway, Tyk) to act as a single entry point for all client requests. This can handle authentication, rate limiting, routing, caching, and more, before forwarding requests to the appropriate backend service, often combined with a Load Balancer.

📈 Data & Performance
Real-time Data Streaming:

Problem: Current API uses a request-response model, which might not be ideal for real-time price updates.

Solution: Implement WebSockets or Server-Sent Events (SSE) to push real-time price updates to connected clients without requiring them to continuously poll the API.

Enhanced Ingestion & Data Sources:

Problem: Relying solely on CoinGecko might have rate limits or coverage limitations.

Solution: Diversify ingestion sources by integrating with multiple cryptocurrency exchanges (e.g., Binance, Coinbase Pro APIs) to ensure higher data reliability, potentially faster updates, and better redundancy. Implement robust error handling and reconciliation for discrepancies.

Historical Data Archiving:

Problem: Storing all historical raw data indefinitely in a hot database can become expensive and impact query performance.

Solution: Implement a data archiving strategy. Periodically move older, less frequently accessed raw data from the primary database to cheaper, long-term storage solutions like object storage (e.g., AWS S3, Google Cloud Storage) or data lakes.

