# SQL Query Generator

A Python-based SQL query generator that helps in generating and managing SQL queries.

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env_template` to `.env` and configure your environment variables:
   ```bash
   cp .env_template .env
   ```

## Development

- Run tests: `python -m unittest discover tests`

## Project Structure

- `query.py`: Main query generation logic
- `db.py`: Database connection and management
- `cache.py`: Caching functionality
- `tests/`: Test suite
- `__sql__/`: Generated SQL queries
- `.env`: Environment variables
- `.env_template`: Template for environment variables
- `requirements.txt`: Project dependencies
- `README.md`: Project documentation
