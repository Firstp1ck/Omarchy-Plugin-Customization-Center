from __future__ import annotations
import ast
import importlib.util
import json
import os
import shutil
from pathlib import Path

from customization_center.core.context import build_context
from customization_center.core.operations import validate_operation
from customization_center.core.paths import Paths
from customization_center.core.registry import load_registry
from customization_center.core.schema_check import load_and_validate, validate

ROOT=Path(__file__).resolve().parents[3]; DIRECTORY=ROOT/"modules/modes"
_spec=importlib.util.spec_from_file_location("modes_contract_helpers",ROOT/"tests/contract/test_module_contract.py")
_helpers=importlib.util.module_from_spec(_spec); assert _spec.loader; _spec.loader.exec_module(_helpers)
_BackendContractVisitor=_helpers._BackendContractVisitor
_conftest_spec=importlib.util.spec_from_file_location("modes_root_conftest",ROOT/"tests/conftest.py")
_root_conftest=importlib.util.module_from_spec(_conftest_spec); assert _conftest_spec.loader; _conftest_spec.loader.exec_module(_root_conftest)

def test_modes_contract_equivalent(tmp_path,monkeypatch):
    home=tmp_path/"home"; config=home/".config"; state=home/".local/state"; cache=home/".cache"; runtime=tmp_path/"runtime"; omarchy=tmp_path/"omarchy"
    for path in (home,config,state,cache,runtime): path.mkdir(parents=True,exist_ok=True)
    shutil.copytree(ROOT/"tests/fixtures/omarchy",omarchy); (config/"omarchy").mkdir(parents=True); shutil.copy2(omarchy/"config/omarchy/shell.json",config/"omarchy/shell.json")
    for name,value in {"HOME":home,"XDG_CONFIG_HOME":config,"XDG_STATE_HOME":state,"XDG_CACHE_HOME":cache,"XDG_RUNTIME_DIR":runtime,"OMARCHY_PATH":omarchy}.items(): monkeypatch.setenv(name,str(value))
    stubs_dir=tmp_path/"stubs"; stubs_dir.mkdir(); stubs=_root_conftest.Stubs(stubs_dir,runtime/"cc-stub.sock"); monkeypatch.setenv("PATH",str(stubs_dir))
    definitions=json.loads((DIRECTORY/"tests/fixtures/contract-stubs.json").read_text()); files=definitions.pop("files")
    for target,source in files.items(): destination=home/target; destination.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(DIRECTORY/"tests/fixtures"/source,destination)
    for name,handler in definitions.items(): stubs(name,handler)
    paths=Paths.from_env(); registry=load_registry(ROOT,[DIRECTORY],paths); entry=registry.view.entry("modes"); module=entry.module
    metadata=load_and_validate(DIRECTORY/"module.json",ROOT/"schemas/module-v1.json")
    status=module.status(build_context("modes","read",paths=paths,registry=registry.view,plugin_dir=ROOT))
    validate(status.data,json.loads((DIRECTORY/metadata["statusSchema"]).read_text()),"status")
    sample=json.loads((DIRECTORY/"tests/fixtures/sample-draft.json").read_text())
    result=module.validate(build_context("modes","validate",paths=paths,registry=registry.view,plugin_dir=ROOT),sample,status)
    assert result.ok and result.normalized_draft is not None
    plan=module.plan(build_context("modes","plan",paths=paths,registry=registry.view,plugin_dir=ROOT),result.normalized_draft,status)
    for operation in plan.operations: validate_operation(operation,paths)
    stubs.close()

def test_modes_imports_obey_contract():
    violations=[]; services=set()
    for source in (DIRECTORY/"backend").rglob("*.py"):
        visitor=_BackendContractVisitor(source,DIRECTORY/"backend"); visitor.visit(ast.parse(source.read_text(),filename=str(source)))
        violations.extend(visitor.violations); services.update(visitor.service_uses)
    assert not violations
    assert services <= set(json.loads((DIRECTORY/"module.json").read_text())["coreServices"])
