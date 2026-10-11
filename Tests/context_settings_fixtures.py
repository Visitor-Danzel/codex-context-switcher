import datetime,json
from pathlib import Path
def fixtures(root):
    root=Path(root).resolve();config=root/'config.toml';catalog=root/'models_cache.json';client=root/'codex-package.json'
    config.write_bytes(b'# fixture\nmodel_context_window = 200000 # retain\nnote="keep"\n')
    catalog.write_text(json.dumps({'client_version':'0.162.0','fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'models':[{'slug':'fixture','context_window':200000,'max_context_window':300000}]}))
    client.write_text(json.dumps({'version':'0.162.0-alpha.17.2'}))
    return config,catalog,client,root/'journal'
def gate():return {'desktop_closed':True,'exclusive_edit':True}
