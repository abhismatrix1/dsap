from pydantic import BaseModel
from typing import Any, Callable, Literal, Optional, Annotated
from typing_extensions import TypedDict, Literal
from prompts import (
    PLANNER_AGENT_SYSTEM_INSTRUCTION,
    READ_AGENT_SYSTEM_INSTRUCTION,
    UPDATE_AGENT_SYSTEM_INSTRUCTION,
    MEMORY_AGENT_SYSTEM_INSTRUCTION
    )



class Topic(BaseModel):
    name: str
    read_tools: list[Callable]
    update_tools: list[Callable]
    knowledge_base_tools: Optional[list[Callable]]

class AgentConfig(BaseModel):
    agent_type: Literal["planner", "read", "update", "orchestrator", "memory", "custom"]
    name: str = ""
    parent_name: str = ""
    tools: list = []
    system_prompt: str = ""
    checkpointer: Any = None
    llm_model: Callable = None
    com_channel: str = "messages"
    msg_history: Literal["all", "last"] = "all"
    co_workers: Optional[list[BaseModel]] = None
    co_workers_abilitiy_str: Optional[list[str]] = None
    routes: Optional[list[BaseModel]] = None
    memory: Optional[BaseModel] = None
    orchestrator: Optional[BaseModel] = None


def _build_agent_config(topic: Topic):
    planner_co_workers = []
    co_workers_abilitiy_str = []
    # build read executor agent
    if len(topic.read_tools) > 0:
        name = f"{topic.name}_read_agent"
        parent_name = f"{topic.name}_agent"
        agent_type = "read"
        tools = topic.read_tools
        com_channel = f"{name}_messages"
        read_agent_config = AgentConfig(name=name,
                                        agent_type=agent_type,
                                        parent_name=parent_name,
                                        tools=tools,
                                        com_channel=com_channel,
                                        system_prompt=READ_AGENT_SYSTEM_INSTRUCTION
                                        )
        tmp = (f"# Co-worker {1} details:\n" +
               f"## Name: {name}\n" +
                "## Abilities:\n" +
                "\n".join(["Ability: "+str(i+1)+t.__doc__ for i,t in enumerate(tools)])
                )
        
        planner_co_workers.append(read_agent_config)
        co_workers_abilitiy_str.append(tmp)
        
    # build update executor agent
    if len(topic.update_tools) > 0:
        name = f"{topic.name}_update_agent"
        parent_name = f"{topic.name}_agent"
        agent_type = "update"
        tools = topic.update_tools
        com_channel = f"{name}_messages"
        update_agent_config = AgentConfig(name=name,
                                        agent_type=agent_type,
                                        parent_name=parent_name,
                                        tools=tools,
                                        com_channel=com_channel,
                                        system_prompt=UPDATE_AGENT_SYSTEM_INSTRUCTION
                                        )
        tmp = (f"# Co-worker {2} details:\n" +
               f"## Name: {name}\n" +
                "## Abilities:\n" +
                "\n".join(["Ability: "+str(i+1)+t.__doc__ for i,t in enumerate(tools)])
                )
        
        planner_co_workers.append(update_agent_config)
        co_workers_abilitiy_str.append(tmp)

    # Build memory agent
    if len(topic.knowledge_base_tools) > 0:
        name = f"{topic.name}_memory_agent"
        parent_name = f"{topic.name}_agent"
        agent_type = "memory"
        tools = topic.knowledge_base_tools
        com_channel = f"{name}_messages"
        sys_instruction = MEMORY_AGENT_SYSTEM_INSTRUCTION
        memory_agent_config = AgentConfig(name=name,
                                        agent_type=agent_type,
                                        tools=tools,
                                        com_channel=com_channel,
                                        system_prompt=sys_instruction
                                        )
    # build planner agent config
    name = f"{topic.name}_agent"
    agent_type = "planner"
    com_channel = f"messages"
    sys_instruction = PLANNER_AGENT_SYSTEM_INSTRUCTION
    sys_instruction += "\n# Below are the details of co-worker available for delegation.\n" + "\n".join(co_workers_abilitiy_str)
    planner_agent_config = AgentConfig(name=name,
                                    agent_type=agent_type,
                                    com_channel=com_channel,
                                    co_workers=planner_co_workers,
                                    co_workers_abilitiy_str=co_workers_abilitiy_str,
                                    memory=memory_agent_config,
                                    system_prompt=sys_instruction
                                    )
    
    
    return planner_agent_config

def build_agent_config(topics: Topic):
    all_agents = []
    for topic in topics:
        all_agents.append(_build_agent_config(topic))
    
    name = "orchestrator_agent"
    orchestrator_agent_config = AgentConfig(name=name,
                                            routes=all_agents,
                                            agent_type="orchestrator")
    for route in orchestrator_agent_config.routes:
        route.orchestrator = orchestrator_agent_config
    return orchestrator_agent_config
