from fastapi import APIRouter, Depends
from neo4j import Driver
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_neo4j_driver, get_settings
from app.api.schemas import AgentTestRequest, AgentTestResponse
from app.core.config import Settings
from app.services import agent_test as service

router = APIRouter(tags=["agent-test"])


@router.post("/agent-test/run", response_model=AgentTestResponse)
def run_agent_test(
    payload: AgentTestRequest,
    session: Session = Depends(get_db_session),
    driver: Driver = Depends(get_neo4j_driver),
    settings: Settings = Depends(get_settings),
):
    return service.run_agent_test(session, driver, settings, payload)
