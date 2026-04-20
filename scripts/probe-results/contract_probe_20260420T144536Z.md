# Contract Probe Report

- Date: 2026-04-20
- Campaign: cmg3twddd0021jl0gesepxuit
- Report ID: contract_probe_20260420T144536Z

## Probe: Item.type wire format (Open Question #2)

### Tested payloads
- `control_weapon`: `{"campaign_id":"cmg3twddd0021jl0gesepxuit","description":"Disposable probe entity for contract validation.","name":"probe-step13-20260420T144536Z-control-weapon","type":"weapon"}`
- `wondrous_item_space`: `{"campaign_id":"cmg3twddd0021jl0gesepxuit","description":"Disposable probe entity for contract validation.","name":"probe-step13-20260420T144536Z-type-space","type":"wondrous item"}`
- `wondrous_item_underscore`: `{"campaign_id":"cmg3twddd0021jl0gesepxuit","description":"Disposable probe entity for contract validation.","name":"probe-step13-20260420T144536Z-type-underscore","type":"wondrous_item"}`
- `wondrous_item_hyphen`: `{"campaign_id":"cmg3twddd0021jl0gesepxuit","description":"Disposable probe entity for contract validation.","name":"probe-step13-20260420T144536Z-type-hyphen","type":"wondrous-item"}`

### Upstream responses
- `control_weapon` -> HTTP 200, accepted=True, body: `{"aliases":[],"campaign_id":"cmg3twddd0021jl0gesepxuit","created_at":"2026-04-20T14:45:37.177000","description":"Disposable probe entity for contract validation.","id":"a4cfbe9b75a842f4b349f491212542c0","image":null,"match_info":null,"name":"probe-step13-20260420T144536Z-control-weapon","tcg_image":null,"type":"weapon","updated_at":null}`
- `wondrous_item_space` -> HTTP 200, accepted=True, body: `{"aliases":[],"campaign_id":"cmg3twddd0021jl0gesepxuit","created_at":"2026-04-20T14:45:45.666000","description":"Disposable probe entity for contract validation.","id":"c2a2508c889b41a29e7f5f3f6ca9cbd7","image":null,"match_info":null,"name":"probe-step13-20260420T144536Z-type-space","tcg_image":null,"type":"wondrous item","updated_at":null}`
- `wondrous_item_underscore` -> HTTP 200, accepted=True, body: `{"aliases":[],"campaign_id":"cmg3twddd0021jl0gesepxuit","created_at":"2026-04-20T14:45:52.448000","description":"Disposable probe entity for contract validation.","id":"161352c3d2f146c78d631d88b05435bd","image":null,"match_info":null,"name":"probe-step13-20260420T144536Z-type-underscore","tcg_image":null,"type":"wondrous_item","updated_at":null}`
- `wondrous_item_hyphen` -> HTTP 200, accepted=True, body: `{"aliases":[],"campaign_id":"cmg3twddd0021jl0gesepxuit","created_at":"2026-04-20T14:45:59.510000","description":"Disposable probe entity for contract validation.","id":"5b3d4266817f4947b91777f0326f89e5","image":null,"match_info":null,"name":"probe-step13-20260420T144536Z-type-hyphen","tcg_image":null,"type":"wondrous-item","updated_at":null}`

### Accepted wire format / shape
- Summary status: `accepted_candidates_found`
- Accepted candidates: `['wondrous_item_space', 'wondrous_item_underscore', 'wondrous_item_hyphen']`

### Validator decision
- Accepted Item.type candidates: ['wondrous_item_space', 'wondrous_item_underscore', 'wondrous_item_hyphen'] Accepted mechanics payload cases: ['typed_object', 'loose_object', 'invalid_scalar']

## Probe: mechanics payload shape (Open Question #3)

### Tested payloads
- `control_no_mechanics`: `{"campaign_id":"cmg3twddd0021jl0gesepxuit","description":"Disposable probe entity for contract validation.","name":"probe-step13-20260420T144536Z-control-no-mech","type":"weapon"}`
- `typed_object`: `{"campaign_id":"cmg3twddd0021jl0gesepxuit","description":"Disposable probe entity for contract validation.","mechanics":{"attunement":false,"damage":"1d8 slashing","mastery":"Sap","notes":"Probe typed payload.","properties":["versatile (1d10)"],"rarity":"rare"},"name":"probe-step13-20260420T144536Z-mech-typed","type":"weapon"}`
- `loose_object`: `{"campaign_id":"cmg3twddd0021jl0gesepxuit","description":"Disposable probe entity for contract validation.","mechanics":{"active":true,"charges":3,"custom_field":{"nested":[1,2,3]},"free_text":"Probe loose payload."},"name":"probe-step13-20260420T144536Z-mech-loose","type":"weapon"}`
- `invalid_scalar`: `{"campaign_id":"cmg3twddd0021jl0gesepxuit","description":"Disposable probe entity for contract validation.","mechanics":"invalid_scalar_payload","name":"probe-step13-20260420T144536Z-mech-invalid-scalar","type":"weapon"}`

### Upstream responses
- `control_no_mechanics` -> HTTP 200, accepted=True, body: `{"aliases":[],"campaign_id":"cmg3twddd0021jl0gesepxuit","created_at":"2026-04-20T14:46:05.250000","description":"Disposable probe entity for contract validation.","id":"6ab9ab597ae94db3a874f57e7cbb9242","image":null,"match_info":null,"name":"probe-step13-20260420T144536Z-control-no-mech","tcg_image":null,"type":"weapon","updated_at":null}`
- `typed_object` -> HTTP 200, accepted=True, body: `{"aliases":[],"campaign_id":"cmg3twddd0021jl0gesepxuit","created_at":"2026-04-20T14:46:11.014000","description":"Disposable probe entity for contract validation.","id":"346e58bff63a4fd09abb066714c89cf1","image":null,"match_info":null,"name":"probe-step13-20260420T144536Z-mech-typed","tcg_image":null,"type":"weapon","updated_at":null}`
- `loose_object` -> HTTP 200, accepted=True, body: `{"aliases":[],"campaign_id":"cmg3twddd0021jl0gesepxuit","created_at":"2026-04-20T14:46:15.283000","description":"Disposable probe entity for contract validation.","id":"23dd28489e6d4b479dd0ecfe09f65649","image":null,"match_info":null,"name":"probe-step13-20260420T144536Z-mech-loose","tcg_image":null,"type":"weapon","updated_at":null}`
- `invalid_scalar` -> HTTP 200, accepted=True, body: `{"aliases":[],"campaign_id":"cmg3twddd0021jl0gesepxuit","created_at":"2026-04-20T14:46:19.394000","description":"Disposable probe entity for contract validation.","id":"4707c150d3a94106997c629d0e5abb13","image":null,"match_info":null,"name":"probe-step13-20260420T144536Z-mech-invalid-scalar","tcg_image":null,"type":"weapon","updated_at":null}`

### Accepted wire format / shape
- Summary status: `accepted_candidates_found`
- Accepted candidates: `['typed_object', 'loose_object', 'invalid_scalar']`

### Cleanup
- `control_weapon` created `a4cfbe9b75a842f4b349f491212542c0`; cleanup_ok=True; cleanup_error=None
- `wondrous_item_space` created `c2a2508c889b41a29e7f5f3f6ca9cbd7`; cleanup_ok=True; cleanup_error=None
- `wondrous_item_underscore` created `161352c3d2f146c78d631d88b05435bd`; cleanup_ok=True; cleanup_error=None
- `wondrous_item_hyphen` created `5b3d4266817f4947b91777f0326f89e5`; cleanup_ok=True; cleanup_error=None
- `control_no_mechanics` created `6ab9ab597ae94db3a874f57e7cbb9242`; cleanup_ok=True; cleanup_error=None
- `typed_object` created `346e58bff63a4fd09abb066714c89cf1`; cleanup_ok=True; cleanup_error=None
- `loose_object` created `23dd28489e6d4b479dd0ecfe09f65649`; cleanup_ok=True; cleanup_error=None
- `invalid_scalar` created `4707c150d3a94106997c629d0e5abb13`; cleanup_ok=True; cleanup_error=None

### DESIGN.md entry checklist
- Copy tested payloads and responses into the `Contract Probe Results` section.
- Close Open Questions #2 and #3 with links to this report.
- Add validator mapping decisions and commit SHA that locks behavior.

_Generated at 20260420T144536Z_
