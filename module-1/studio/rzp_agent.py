from langchain_core.messages import AnyMessage, AIMessage, ToolMessage, SystemMessage, RemoveMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent, tools_condition, ToolNode
from langgraph.types import Command

from typing import Any, Callable, Literal, Annotated, Union
from typing_extensions import TypedDict, Literal
from typing import List, Tuple
from trustcall import create_extractor

from pydantic import BaseModel, Field
from functools import partial


from langchain_openai import AzureChatOpenAI


def create_executor_agent(graph_state, config):

    prebuilt_agent = create_react_agent(
        llm_model,
        checkpointer=config.checkpointer,
        tools=config.tools, 
        state_modifier=config.system_prompt,
    )

    def agent_node(state: graph_state
                   ) -> Command[Literal[config.parent_name]]:
        sender_channel = "messages"
        if config.msg_history == "last":
            messages = {"messages": state[config.com_channel][-1].content}
        else:
            messages = {"messages": state[config.com_channel]}
        response = prebuilt_agent.invoke(messages, debug=False)
        
        return Command(
            update={
                config.com_channel: [
                    AIMessage(content=f"{config.name} coworker reply: " + response["messages"][-1].content, name=config.name)
                ],
                sender_channel: [
                    AIMessage(content=f"{config.name} coworker reply: " + response["messages"][-1].content, name=config.name)
                ],
                "last_message_from": config.name

            },
            # We want our workers to ALWAYS "report back" to the supervisor when done
            goto=config.parent_name,
        )
    return agent_node

def create_planner_agent(
        graph_state,
        config
        ):
    
    class DelegateToCoworker(BaseModel):
        co_worker_name: str = Field(
            description="co-worker name to delegate"
        )
        co_worker_task: str = Field(
            description="Description and details of the current task co-worker has to execute. do not include description of the agent ability."
        )
        intermediate_response: str = Field(
            description=("We need to keep communicating with the user about. our conversation should not look mechanical."
                         "you can respond like 'ok let me check, please hold on for a moment' etc. Do not tell what exact process you are going to do. we nned not disclose internal working")
        )

    class Response(BaseModel):
        response: str = Field(description="response for sending it to the user user.")
    
    class Router(BaseModel):
        """Worker to route to next. If no workers needed, respond using Response."""

        thought: str = Field(description="reason for this step.")
        action: Union[DelegateToCoworker, Response] = Field(
            description="Action to perform. If you want to respond to user, use Response. "
            "If you need to further use tools to get the answer, use DelegateToCoworker."
        )

    class ReturnToOrchestrator(BaseModel):
        retun_message: str = Field(description="If the user request has wrongly being sent to you then return to Orchestrator agent saying your department does not handle such querries.")

    class Router2(BaseModel):
        """Worker to route to next. If no workers needed, respond using Response."""

        thought: str = Field(description="reason for this step.")
        action: Union[DelegateToCoworker, Response, ReturnToOrchestrator] = Field(
            description="Action to perform. If you want to respond to user, use Response. "
            "If you need get work done to get the answer, use DelegateToCoworker. "
            "If you do not handle such request then return to Orchestrator, use ReturnToOrchestrator  "
        )
    
    if config.orchestrator:
        router_trust_call = create_extractor(llm_model, tools=[Router2], tool_choice="Router2")
    else:
        router_trust_call = create_extractor(llm_model, tools=[Router], tool_choice="Router")

    def planner_node(state: graph_state) -> Command[Literal[*[cw.name for cw in config.co_workers], END]]:
        """if config.user_profile_key not in state.keys:
            user_profile = load_user_profile()
        else:
            user_profile = state.get(config.user_profile_key)"""
        
        co_workers = {cw.name:cw.com_channel for cw in config.co_workers}
        messages = [
            {"role": "system", "content": config.system_prompt.format(latest_memory=state["latest_memory"], mechant_profile="NA")},
        ] + state[config.com_channel]

        response = router_trust_call.invoke(messages)["responses"][0]
        if isinstance(response.action, DelegateToCoworker):
            itm_resp = response.action.intermediate_response
            if response.action.co_worker_name in co_workers.keys():
                goto = [response.action.co_worker_name]
            else:
                raise ValueError(f"co-worker name is not in list {response}")
        elif isinstance(response.action, Response):
            goto = END
        elif isinstance(response.action, ReturnToOrchestrator):
            print("return to orchestrator")
            goto = [config.orchestrator.name]
        else:
            raise ValueError(f"wrong output from trust call  {response}") 
        
        if goto == END:
            return Command(
            update={
                config.com_channel: [
                    AIMessage(
                        content="Thought: " + response.thought+ "\nresponse_to_user: " + response.action.response, name="planner"
                    )
                ],
                "last_message_from":config.name
            },
            goto=END)
        else:
            return Command(
            update={co_workers[response.action.co_worker_name]:
                [AIMessage(
                    content="Thought: " + response.thought+ "\ncoworker_name: " + response.action.co_worker_name + "\ncoworker_task:" + response.action.co_worker_task, name="planner"
                ) ],
                "last_message_from":config.name,
                "messages": [AIMessage(
                    content="Thought: " + response.thought+ "\ncoworker_name: " + response.action.co_worker_name + "\ncoworker_task:" + response.action.co_worker_task, name="planner"
                ) ,
                AIMessage(content="response_to_user: " + itm_resp, name="planner")] if state["last_message_from"]=='memory_agent' else [],
            },
            goto=goto
            )
        
    return planner_node

def create_orchestrator_agent(graph_state, config):

    class Router(BaseModel):
        """Worker to route to next. If no workers needed, respond using Response."""

        thought: str = Field(description="reason for this step.")
        action: Literal[*[cw.name for cw in config.routes]] = Field(
            description=f"agent to route. must be any of these  {[cw.name for cw in config.routes]}"
        
        )

    if len(config.routes) > 1:
        edges = Literal[*[cw.name for cw in config.routes], END]
        router_trust_call = create_extractor(llm_model, tools=[Router], tool_choice="Router")
    else:
        edges = Literal[*[cw.name for cw in config.routes]]
    
    def orchestrator_node(state: graph_state) -> Command[edges]:
        if len(config.routes) == 1:
            goto = config.routes[0].name
            return Command(
                goto=goto
            )
        messages = [
            {"role": "system", "content": config.system_prompt},
        ] + state[config.com_channel]

        response = router_trust_call.invoke(messages)["responses"][0]
        goto = response.action
        return Command(
            goto=goto
            )
    return orchestrator_node
        
def create_memory_agent(graph_state, config):

    llm_model_ = llm_model.bind_tools(config.tools)
    
    def should_load_memory(state: graph_state, flash_memory_key: str = "latest_memory"):
        
        if state.get(flash_memory_key, ""):
                latest_memory = state[flash_memory_key]
        else:
                latest_memory = "No knowledge retrived yet"
        user_message = state["messages"][-1].content
        system_prompt = config.system_prompt.format(user_message=user_message, latest_memory=latest_memory)
        response  = llm_model_.invoke([SystemMessage(content=system_prompt)])
        return {config.com_channel:[response]}
    
    def refresh_memory(state: graph_state, flash_memory_key: str = "latest_memory"):
        last_mesage = state[config.com_channel][-1].copy()
        delete_messages = [RemoveMessage(id=m.id) for m in state[config.com_channel]]
        if isinstance(last_mesage, ToolMessage):
            print("tool message")
            return {flash_memory_key: last_mesage.content,
                    config.com_channel: delete_messages,
                    "last_message_from": "memory_agent"}
            
        else:
            print("no tool message")
            return {config.com_channel: delete_messages,
                    "last_message_from": "memory_agent"}
    
    builder = StateGraph(graph_state)
    builder.add_node("should_load_memory", should_load_memory)
    builder.add_node("tools", ToolNode(config.tools, messages_key=config.com_channel))
    builder.add_node("memory_refresh", refresh_memory)

    builder.add_edge(START, "should_load_memory")
    builder.add_conditional_edges(
        "should_load_memory",
        # If the latest message (result) from assistant is a tool call -> tools_condition routes to tools
        # If the latest message (result) from assistant is a not a tool call -> tools_condition routes to END
        partial(tools_condition, messages_key=config.com_channel),
        {"tools":"tools", END:"memory_refresh"}
        )
    builder.add_edge("tools", "memory_refresh")
    builder.add_edge("memory_refresh", END)
    memory_agent = builder.compile(checkpointer=config.checkpointer)
    return memory_agent

        