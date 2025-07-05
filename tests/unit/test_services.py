# tests/unit/test_services.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone
import asyncio

# Import the services to be tested
from app.services import ingestion_service
from app.services import aggregation_service
from app.services import cache_service
from app.crud import token_price as crud_token_price
from app.schemas.token_price import TokenPriceCreate
from app.models.token_price import TokenPrice # Used for mock DB query results
from app.core.config import settings

# --- Fixtures for common mocks ---

@pytest.fixture
def mock_db_session(mocker):
    """Mocks a SQLAlchemy DB session."""
    session_mock = mocker.MagicMock()
    # Mock specific methods that services might call
    session_mock.add = mocker.MagicMock()
    session_mock.commit = mocker.MagicMock()
    session_mock.refresh = mocker.MagicMock()
    session_mock.rollback = mocker.MagicMock()
    return session_mock

@pytest.fixture(autouse=True)
def mock_session_local(mocker, mock_db_session):
    """Patches SessionLocal to return our mock session."""
    mocker.patch('app.core.db.SessionLocal', return_value=mock_db_session)

@pytest.fixture(autouse=True)
def mock_logger(mocker):
    """Mocks the logger to prevent actual logging during tests."""
    return mocker.patch('app.services.ingestion_service.logger'), \
           mocker.patch('app.services.aggregation_service.logger'), \
           mocker.patch('app.services.cache_service.logger')

# --- Unit Tests for Ingestion Service ---

@pytest.mark.asyncio
async def test_fetch_price_from_coingecko_success(mocker):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"bitcoin": {"usd": 35000.0}}
    mock_response.raise_for_status = MagicMock() # Should not be called on success

    mocker.patch('httpx.AsyncClient.get', AsyncMock(return_value=mock_response))

    price = await ingestion_service.fetch_price_from_coingecko("bitcoin")
    assert price == 35000.0
    ingestion_service.httpx.AsyncClient.get.assert_called_once()

@pytest.mark.asyncio
async def test_fetch_price_from_coingecko_http_error(mocker):
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"
    mock_response.raise_for_status = MagicMock(side_effect=ingestion_service.httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response))

    mocker.patch('httpx.AsyncClient.get', AsyncMock(return_value=mock_response))

    with pytest.raises(ingestion_service.httpx.HTTPStatusError):
        await ingestion_service.fetch_price_from_coingecko("nonexistent_token")
    ingestion_service.httpx.AsyncClient.get.assert_called_once()

@pytest.mark.asyncio
async def test_fetch_price_from_coingecko_network_error(mocker):
    mocker.patch('httpx.AsyncClient.get', AsyncMock(side_effect=ingestion_service.httpx.RequestError("Network Down", request=MagicMock())))

    with pytest.raises(ingestion_service.httpx.RequestError):
        await ingestion_service.fetch_price_from_coingecko("bitcoin")
    ingestion_service.httpx.AsyncClient.get.assert_called_once()

@pytest.mark.asyncio
async def test_fetch_price_from_coingecko_data_error(mocker):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"bitcoin": {}} # Missing 'usd'
    mock_response.raise_for_status = MagicMock()

    mocker.patch('httpx.AsyncClient.get', AsyncMock(return_value=mock_response))

    with pytest.raises(ValueError, match="Price for bitcoin not found"):
        await ingestion_service.fetch_price_from_coingecko("bitcoin")

@pytest.mark.asyncio
async def test_ingest_token_price_success(mocker, mock_db_session):
    mocker.patch('app.services.ingestion_service.fetch_price_from_coingecko', AsyncMock(return_value=36000.0))
    mocker.patch('app.crud.token_price.create_token_price', MagicMock())

    await ingestion_service.ingest_token_price("ethereum")

    ingestion_service.fetch_price_from_coingecko.assert_called_once_with("ethereum", "usd")
    crud_token_price.create_token_price.assert_called_once()
    args, _ = crud_token_price.create_token_price.call_args
    price_data = args[1] # The TokenPriceCreate object
    assert price_data.token_symbol == "ETHEREUM"
    assert price_data.price == 36000.0
    assert price_data.granularity == "5min"
    mock_db_session.close.assert_called_once()

@pytest.mark.asyncio
async def test_ingest_token_price_failure_closes_db(mocker, mock_db_session):
    mocker.patch('app.services.ingestion_service.fetch_price_from_coingecko', AsyncMock(side_effect=Exception("API Error")))
    mocker.patch('app.crud.token_price.create_token_price', MagicMock())

    await ingestion_service.ingest_token_price("ethereum") # No raise, handles internally

    mock_db_session.close.assert_called_once()
    crud_token_price.create_token_price.assert_not_called()

@pytest.mark.asyncio
async def test_start_ingestion_loop_runs_once(mocker):
    mock_ingest = mocker.patch('app.services.ingestion_service.ingest_token_price', AsyncMock())
    mock_sleep = mocker.patch('asyncio.sleep', AsyncMock())

    # Run the loop for a very short duration and break after first iteration
    async def run_and_break():
        await ingestion_service.start_ingestion_loop(interval_minutes=1, symbols=["BTC", "ETH"])
        # This will never be reached in a real loop, but for testing, we can
        # set a side_effect on sleep to break the loop after the first iteration.
    
    # We need to ensure that the loop executes at least once and then breaks.
    # The first call to sleep should pause the loop. We can then raise an error
    # to stop it.
    mock_sleep.side_effect = [None, asyncio.CancelledError] # First sleep succeeds, second cancels task

    with pytest.raises(asyncio.CancelledError):
        await run_and_break()

    assert mock_ingest.call_count == 2 # Called for BTC and ETH
    mock_ingest.assert_any_call("BTC")
    mock_ingest.assert_any_call("ETH")
    mock_sleep.assert_called_once() # Only one sleep call before cancellation

# --- Unit Tests for Aggregation Service ---

@pytest.mark.asyncio
async def test_run_hourly_aggregation_success(mocker, mock_db_session):
    # Mock data from get_hourly_aggregates
    mock_agg_data = [
        MagicMock(token_symbol="BTC", timestamp_hour_str="2023-01-01 10:00:00", price_avg=100.0, price_high=101.0, price_low=99.0, num_data_points=10),
        MagicMock(token_symbol="ETH", timestamp_hour_str="2023-01-01 10:00:00", price_avg=200.0, price_high=202.0, price_low=198.0, num_data_points=12),
    ]
    mocker.patch('app.crud.token_price.get_hourly_aggregates', MagicMock(return_value=mock_agg_data))
    mocker.patch('app.crud.token_price.create_token_price', MagicMock())

    await aggregation_service.run_hourly_aggregation()

    crud_token_price.get_hourly_aggregates.assert_called_once()
    assert crud_token_price.create_token_price.call_count == len(mock_agg_data)
    mock_db_session.commit.assert_called_once()
    mock_db_session.close.assert_called_once()

@pytest.mark.asyncio
async def test_run_hourly_aggregation_no_data(mocker, mock_db_session):
    mocker.patch('app.crud.token_price.get_hourly_aggregates', MagicMock(return_value=[]))
    mocker.patch('app.crud.token_price.create_token_price', MagicMock())

    await aggregation_service.run_hourly_aggregation()

    crud_token_price.get_hourly_aggregates.assert_called_once()
    crud_token_price.create_token_price.assert_not_called()
    mock_db_session.commit.assert_not_called() # No data, no commit
    mock_db_session.close.assert_called_once()

@pytest.mark.asyncio
async def test_run_daily_aggregation_success(mocker, mock_db_session):
    mock_agg_data = [
        MagicMock(token_symbol="BTC", timestamp_day_str="2023-01-01 00:00:00", price_avg=1000.0, price_high=1010.0, price_low=990.0, num_data_points=100),
    ]
    mocker.patch('app.crud.token_price.get_daily_aggregates', MagicMock(return_value=mock_agg_data))
    mocker.patch('app.crud.token_price.create_token_price', MagicMock())

    await aggregation_service.run_daily_aggregation()

    crud_token_price.get_daily_aggregates.assert_called_once()
    assert crud_token_price.create_token_price.call_count == len(mock_agg_data)
    mock_db_session.commit.assert_called_once()
    mock_db_session.close.assert_called_once()

@pytest.mark.asyncio
async def test_run_aggregation_loop_runs_hourly_and_daily_once(mocker):
    mock_hourly_agg = mocker.patch('app.services.aggregation_service.run_hourly_aggregation', AsyncMock())
    mock_daily_agg = mocker.patch('app.services.aggregation_service.run_daily_aggregation', AsyncMock())
    mock_sleep = mocker.patch('asyncio.sleep', AsyncMock())

    # Simulate being at 00:05 UTC for daily aggregation trigger
    fixed_time = datetime(2023, 1, 2, 0, 5, 0, tzinfo=timezone.utc)
    mocker.patch('app.services.aggregation_service.datetime', MagicMock(now=MagicMock(return_value=fixed_time)))

    async def run_and_break():
        await aggregation_service.start_aggregation_loop(interval_minutes=60)
    
    mock_sleep.side_effect = [None, asyncio.CancelledError] # Allow first sleep, then cancel

    with pytest.raises(asyncio.CancelledError):
        await run_and_break()

    mock_hourly_agg.assert_called_once()
    mock_daily_agg.assert_called_once() # Should be called because of fixed_time
    mock_sleep.assert_called_once()

@pytest.mark.asyncio
async def test_run_data_retention_job_deletes_old_data(mocker, mock_db_session):
    mock_query_filter = MagicMock()
    mock_query_filter.delete = MagicMock(return_value=5) # 5 rows deleted
    mock_db_session.query.return_value.filter.return_value = mock_query_filter

    mock_sleep = mocker.patch('asyncio.sleep', AsyncMock(side_effect=asyncio.CancelledError))
    mocker.patch.object(settings, 'DATA_RETENTION_RAW_DAYS', 1) # Set retention to 1 day for test

    with pytest.raises(asyncio.CancelledError):
        await aggregation_service.run_data_retention_job()

    mock_db_session.query.assert_called_once_with(TokenPrice)
    mock_query_filter.delete.assert_called_once_with(synchronize_session=False)
    mock_db_session.commit.assert_called_once()
    mock_sleep.assert_called_once_with(6 * 3600)

# --- Unit Tests for Cache Service ---

@pytest.mark.asyncio
async def test_cache_set_get(mocker):
    await cache_service.set_cache("test_key", {"data": "value"}, expire=10)
    result = await cache_service.get_cache("test_key")
    assert result == {"data": "value"}

@pytest.mark.asyncio
async def test_cache_get_expired(mocker):
    await cache_service.set_cache("expired_key", {"data": "expired_value"}, expire=1)
    await asyncio.sleep(1.1) # Wait for cache to expire
    result = await cache_service.get_cache("expired_key")
    assert result is None
    assert "expired_key" not in cache_service._cache # Ensure it's removed

@pytest.mark.asyncio
async def test_cache_invalidate(mocker):
    await cache_service.set_cache("invalid_key", {"data": "to_invalidate"}, expire=100)
    assert await cache_service.get_cache("invalid_key") is not None
    await cache_service.invalidate_cache("invalid_key")
    assert await cache_service.get_cache("invalid_key") is None

@pytest.mark.asyncio
async def test_cache_cleanup_loop_removes_expired_items(mocker):
    mocker.patch('asyncio.sleep', AsyncMock(side_effect=[None, asyncio.CancelledError])) # Allow one sleep cycle then cancel
    
    # Add an expired item
    expired_time = datetime.now() - timedelta(seconds=1)
    cache_service._cache["old_item"] = ({"data": "old"}, expired_time)
    
    # Add a fresh item
    fresh_time = datetime.now() + timedelta(seconds=10)
    cache_service._cache["new_item"] = ({"data": "new"}, fresh_time)

    with pytest.raises(asyncio.CancelledError):
        await cache_service._cache_cleanup_loop(interval_seconds=1)
    
    assert "old_item" not in cache_service._cache
    assert "new_item" in cache_service._cache