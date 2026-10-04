import json
import pytest
from fastapi.testclient import TestClient
from mirage.api.app import create_app
from mirage.environments.binder import BinderBioPOMDP, BinderWorldMode
from mirage.integration import CampaignController, make_receptor_binder_service
from mirage.provenance import PublicRecordStore, Replay, verify_deterministic_source

MODES=(("instability",BinderWorldMode.SINGLE_FAILURE),("aggregation_kinetic_defect",BinderWorldMode.COMPOUND_FAILURE),("broken_assay",BinderWorldMode.ASSAY_FAILURE),("invalid_biological_model",BinderWorldMode.MODEL_FAILURE),("misleading_proxy_trap",BinderWorldMode.MIXED))
BAD=("ground_truth","privileged_state","simulator_truth","world_mode","hidden","latent","compound_failure","single_failure","assay_failure","model_failure")
def public(value):
    text=json.dumps(value,sort_keys=True,default=str).lower()
    assert not [x for x in BAD if x in text],text

@pytest.mark.parametrize(("name","mode"),MODES)
def test_h1_showcase_public_and_deterministic(tmp_path,name,mode):
    c=CampaignController(PublicRecordStore(tmp_path/name))
    c.reset(9,mode,policy_name="rescue_planner")
    while not c.step().terminal: pass
    r=c.record()
    assert verify_deterministic_source(r,lambda: BinderBioPOMDP(mode))==[]
    public(r.model_dump(mode="json")); public([x.model_dump(mode="json") for x in Replay(r)])
    public(c.session.summary().model_dump(mode="json")); public(vars(c.policy))

def test_h1_api_full_flow_and_boundary(tmp_path):
    app=create_app(make_receptor_binder_service(PublicRecordStore(tmp_path),scenario=BinderWorldMode.COMPOUND_FAILURE))
    client=TestClient(app); reset=client.post("/episodes",json={"seed":9,"policy_name":"rescue_planner"})
    eid=reset.json()["episode_id"]; payloads=[reset.json()]; actions=[]
    for _ in range(6):
        rec=client.get(f"/episodes/{eid}/recommendation"); action=rec.json()["action"]
        step=client.post(f"/episodes/{eid}/actions",json=action); actions.append(action["action_type"]); payloads += [rec.json(),step.json()]
        if step.json()["state"]["terminal"]: break
    replay=client.get(f"/episodes/{eid}/replay")
    assert actions[:3]==["MEASURE_SEC","REDESIGN_SOLUBILITY","MEASURE_SPR"] and replay.json()["complete"]
    public(payloads+[replay.json()])

def test_h1_same_seed_replays_identically(tmp_path):
    def run(root):
        c=CampaignController(PublicRecordStore(root)); c.reset(17,BinderWorldMode.COMPOUND_FAILURE,policy_name="rescue_planner")
        while not c.step().terminal: pass
        return c.record()
    assert run(tmp_path/"one").model_dump(mode="json")==run(tmp_path/"two").model_dump(mode="json")
