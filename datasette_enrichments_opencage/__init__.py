from __future__ import annotations
from datasette import hookimpl

import typing as t
if t.TYPE_CHECKING:
    from datasette.app import Datasette

from datasette_enrichments import Enrichment
from datasette.database import Database
from wtforms import (
    Form,
    StringField,
    TextAreaField,
    PasswordField,
)
from wtforms.validators import DataRequired
import httpx
import json
import secrets
import sqlite_utils
from datasette.plugins import pm
from . import hookspecs
from datasette.utils import await_me_maybe

pm.add_hookspecs(hookspecs)

@hookimpl
def register_enrichments(datasette):
    return [OpenCageEnrichment()]


class OpenCageEnrichment(Enrichment):
    @property
    def name(self):
        return "OpenCage geocoder"
    
    @property
    def slug(self):
        return "opencage"
    
    description = "Geocode to latitude/longitude points using OpenCage"
    batch_size = 10
    log_traceback = True

    async def get_config_form(self, datasette: Datasette, db: Database, table: str):
        def get_text_columns(conn):
            db = sqlite_utils.Database(conn)
            return [
                key for key, value in db[table].columns_dict.items() if value is str
            ]

        text_columns = await db.execute_fn(get_text_columns)

        class ConfigForm(Form):
            input = TextAreaField(
                "Geocode input",
                description="A template to run against each row to generate geocoder input. Use {{ COL }} for columns.",
                validators=[DataRequired(message="Prompt is required.")],
                default=" ".join(["{{ %s }}" % c for c in text_columns]),
            )
            json_column = StringField(
                "Store JSON in column",
                description="To store full JSON from OpenCage, enter a column name here",
                render_kw={
                    "placeholder": "Leave this blank if you only want to store latitude/longitude"
                },
            )

        def stash_api_key(form, field):
            if not hasattr(datasette, "_enrichments_opencage_stashed_keys"):
                datasette._enrichments_opencage_stashed_keys = {}
            key = secrets.token_urlsafe(16)
            datasette._enrichments_opencage_stashed_keys[key] = field.data
            field.data = key

        class ConfigFormWithKey(ConfigForm):
            api_key = PasswordField(
                "API key",
                description="Your OpenCage API key",
                validators=[
                    DataRequired(message="API key is required."),
                    stash_api_key,
                ],
            )

        plugin_config = datasette.plugin_config("datasette-enrichments-opencage") or {}
        api_key = plugin_config.get("api_key")

        return ConfigForm if api_key else ConfigFormWithKey

    async def enrich_batch(self, rows, datasette, db, table, pks, config):
        budget_check = None
        for result in pm.hook.datasette_enrichments_register_budget_check(
            datasette=datasette,
          ):
          budget_check = await await_me_maybe(result)
          break
        
        amount = len(rows)
        tx = None
        
        if budget_check:
          tx = await budget_check.reserve(amount=amount)
          if not tx:
              raise Exception("Budget check failed, not enriching")
          
        # TODO: catch errors, settle the # of successful attempts
        for row in rows:
          geocode_data = await self.call_opencage_api(row, datasette, config)
          await self.update_database(
              db=db,
              table=table,
              pks=pks,
              row=row,
              geocode_data=geocode_data,
              config=config
          )
        
        # Settle the transaction, if any
        if budget_check and tx:
          await budget_check.settle(
              tx=tx,
              amount=amount,
              meta={"table": table, "pk_values": [row[pk] for pk in pks]},
          )
    
    async def call_opencage_api(self, row, datasette, config):
        """Make an API call to OpenCage and return the geocode data."""
        url = "https://api.opencagedata.com/geocode/v1/json"
        params = {
            "key": resolve_api_key(datasette, config),
            "limit": 1,
        }
        json_column = config.get("json_column")
        if not json_column:
            params["no_annotations"] = 1
        
        # Build the geocode input from the template
        input_text = config["input"]
        for key, value in row.items():
            input_text = input_text.replace("{{ %s }}" % key, str(value or "")).replace(
                "{{%s}}" % key, str(value or "")
            )
        params["q"] = input_text
        
        # Make the API request
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if not data["results"]:
            raise ValueError("No results found for {}".format(input_text))
        
        return data

    async def update_database(self, db, table, pks, row, geocode_data, config):
        """Update the database with geocode results."""
        result = geocode_data["results"][0]
        update = {
            "latitude": result["geometry"]["lat"],
            "longitude": result["geometry"]["lng"],
        }
        
        json_column = config.get("json_column")
        if json_column:
            update[json_column] = json.dumps(geocode_data)

        ids = [row[pk] for pk in pks]

        def do_update(conn):
            with conn:
                db = sqlite_utils.Database(conn)
                db[table].update(ids, update, alter=True)

        await db.execute_write_fn(do_update)
      
class ApiKeyError(Exception):
    pass


def resolve_api_key(datasette, config):
    plugin_config = datasette.plugin_config("datasette-enrichments-opencage") or {}
    api_key = plugin_config.get("api_key")
    if api_key:
        return api_key
    # Look for it in config
    api_key_name = config.get("api_key")
    if not api_key_name:
        raise ApiKeyError("No API key reference found in config")
    # Look it up in the stash
    if not hasattr(datasette, "_enrichments_opencage_stashed_keys"):
        raise ApiKeyError("No API key stash found")
    stashed_keys = datasette._enrichments_opencage_stashed_keys
    if api_key_name not in stashed_keys:
        raise ApiKeyError("No API key found in stash for {}".format(api_key_name))
    return stashed_keys[api_key_name]
