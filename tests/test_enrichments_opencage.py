from datasette.app import Datasette
from datasette_enrichments.utils import wait_for_job
import pytest
import re
import sqlite_utils


@pytest.fixture
def non_mocked_hosts():
    # This ensures httpx-mock will not affect Datasette's own
    # httpx calls made in the tests by datasette.client:
    return ["localhost"]


@pytest.mark.asyncio
@pytest.mark.parametrize("api_key_from_config", (True, False))
async def test_enrichment(tmpdir, api_key_from_config, httpx_mock):
    httpx_mock.add_response(
        url=re.compile(r"https://api.opencagedata.com/geocode/v1/json.*"),
        method="GET",
        json={
            "results": [
                {
                    "geometry": {
                        "lat": 38.8976633,
                        "lng": -77.0365739,
                    }
                }
            ]
        },
    )
    db_path = str(tmpdir / "data.db")
    db = sqlite_utils.Database(db_path)
    db["addresses"].insert(
        {"id": 1, "address": "1600 Pennsylvania Ave NW, Washington, DC 20500"},
        pk="id",
    )

    metadata = {}
    if api_key_from_config:
        metadata["plugins"] = {"datasette-enrichments-opencage": {"api_key": "abc123"}}
    datasette = Datasette([db_path], metadata=metadata)

    cookies = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}
    csrftoken = (
        await datasette.client.get("/-/enrich/data/addresses/opencage", cookies=cookies)
    ).cookies["ds_csrftoken"]
    cookies["ds_csrftoken"] = csrftoken

    post = {
        "input": "{{ address }}",
        "csrftoken": cookies["ds_csrftoken"],
    }
    if not api_key_from_config:
        post["api_key"] = "abc123"

    response = await datasette.client.post(
        "/-/enrich/data/addresses/opencage",
        data=post,
        cookies=cookies,
    )
    assert response.status_code == 302

    job_id = response.headers["Location"].split("=")[-1]
    await wait_for_job(datasette, job_id, timeout=1)

    assert db["addresses"].columns_dict == {
        "id": int,
        "address": str,
        "latitude": float,
        "longitude": float,
    }

    # Check the API key was used
    request = httpx_mock.get_request()
    assert request.url.params["key"] == "abc123"
