import sys
sys.path.append('/Users/abhishek.kushwaha/projects/langchain-academy/module-1/studio')
sys.path.append('/Users/abhishek.kushwaha/projects/langchain-academy/module-1')
from rzp_agent import create_executor_agent, create_planner_agent, create_memory_agent, create_orchestrator_agent
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel, Field
from functools import partial

from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from typing_extensions import TypedDict
from typing import Any, Callable, Literal, Annotated, Optional
from prompts import READ_AGENT_SYSTEM_INSTRUCTION, UPDATE_AGENT_SYSTEM_INSTRUCTION, PLANNER_AGENT_SYSTEM_INSTRUCTION


import sqlite3
# In memory
conn = sqlite3.connect(":memory:", check_same_thread = False)
checkpointer = SqliteSaver(conn)

state_dict = {
    "messages": Annotated[list[AnyMessage], add_messages],
    "merchant_profile": str,
    "latest_memory": str,
    "last_message_from": Literal["memory_agent", "read_agent", "tool", "other"],
}


class CustomerSuportAgent:
    def __init__(self, config):
        self.csa_config = config
        self.topic_team = []
    
    def build(self, ):
        # create state dict channels
        for topic_agent_config in self.csa_config.routes:
            for executor_agent_config in topic_agent_config.co_workers:
                state_dict[executor_agent_config.com_channel] = Annotated[list[AnyMessage], add_messages]
            state_dict[topic_agent_config.memory.com_channel] = Annotated[list[AnyMessage], add_messages]

        
        AgentState = TypedDict("AgentState", state_dict)
        orchestrator_Agent = "topic_orchestrator"
        # Co-wroker 1 details:
        ## Name: {read_agent_name}
        ## Description: {read_team}
        for topic_agent_config in self.csa_config.routes:
            exeutor_agents = []
            for executor_agent_config in topic_agent_config.co_workers:
                exeutor_agents.append(create_executor_agent(AgentState, executor_agent_config))
            memory_agent = create_memory_agent(AgentState, topic_agent_config.memory)
            planner_agent = create_planner_agent(AgentState, topic_agent_config)
        
            agent_builder = StateGraph(AgentState)
            agent_builder.add_node(topic_agent_config.memory.name, memory_agent)
            agent_builder.add_node(topic_agent_config.name, planner_agent)
            for exeutor_agent, exeutor_agent_config in zip(exeutor_agents, topic_agent_config.co_workers):
                agent_builder.add_node(exeutor_agent_config.name, exeutor_agent)

            agent_builder.add_edge(START, topic_agent_config.memory.name)
            agent_builder.add_edge(topic_agent_config.memory.name, topic_agent_config.name)
            final_agent = agent_builder.compile(checkpointer=checkpointer)
            self.topic_team.append(final_agent)

        orchestrator_agent = create_orchestrator_agent(AgentState, self.csa_config)
        agent_builder = StateGraph(AgentState)
        agent_builder.add_node(self.csa_config.name, orchestrator_agent)
        for each_agent, each_agent_config in zip(self.topic_team, self.csa_config.routes):
            agent_builder.add_node(each_agent_config.name, each_agent)

        agent_builder.add_edge(START, self.csa_config.name)
        final_agent = agent_builder.compile(checkpointer=checkpointer)
        return final_agent
        
        #return self.topic_team[0]
    
if __name__ == "__main__":
    from memory_tools import past_successful_example
    from razorpay_tools import (get_billing_label_suggestions, 
                                get_feature_status, 
                                create_api_key, 
                                get_merchant_config, 
                                get_refund_source, 
                                toggle_fee_bearer,
                                update_refund_source,
                                get_bank_account_details_tool,
                                get_email_address_tool,
                                update_contact_name,
                                get_website_verification_status,
                                get_merchant_details)
    class Topic(BaseModel):
        name: str
        read_tools: list[Callable]
        update_tools: list[Callable]
        knowledge_base_tools: Optional[list[Callable]]
    topic1 = Topic(topic="Activations",
          read_tools=[get_feature_status,
                      get_merchant_config],
          update_tools=[toggle_fee_bearer,
                        update_refund_source],
        knowledge_base_tools=[past_successful_example]
                      )
    
    topic2 = Topic(topic="Accounts",
          read_tools=[get_feature_status,
                      get_merchant_config],
          update_tools=[toggle_fee_bearer,
                        update_refund_source],
        knowledge_base_tools=[past_successful_example]
                      )
    
    topic3 = Topic(topic="TSR",
          read_tools=[get_feature_status,
                      get_merchant_config],
          update_tools=[toggle_fee_bearer,
                        update_refund_source],
        knowledge_base_tools=[past_successful_example]
                      )
    
    CSA = CustomerSuportAgent([topic1, topic2, topic3]).build()
    (CSA.get_graph(xray=True).draw_mermaid_png(output_file_path="/Users/abhishek.kushwaha/projects/langchain-academy/module-1/test_grph.png"))
    print(CSA)

