import os
import sys
from dotenv import load_dotenv # add pinecone key and jina ai key in .env file.

from pinecone import Pinecone
from pydantic import Field
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.core import VectorStoreIndex
from llama_index.embeddings.jinaai import JinaEmbedding
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings

import sys
sys.path.append('/Users/abhishek.kushwaha/projects/chatAgent/src')

embeddings = OllamaEmbeddings(
    model='mxbai-embed-large',
)
fd_store = FAISS.load_local(
    "/Users/abhishek.kushwaha/projects/chatAgent/src/data/indexes/FD_resolution", embeddings, allow_dangerous_deserialization=True
)

knowledge_store = FAISS.load_local(
    "/Users/abhishek.kushwaha/projects/chatAgent/src/data/indexes/auto_policy", embeddings, allow_dangerous_deserialization=True
)

load_dotenv("/Users/abhishek.kushwaha/projects/langchain-academy/module-1/.env")

pinecone_api_key = os.getenv("PINECONE_API_KEY")
jina_ai_api_key = os.getenv("JINA_API_KEY")
print("here", pinecone_api_key, jina_ai_api_key)

def get_rag_engine(idx_name = "jina-ai-razorpay-payment-unique"):
    pc = Pinecone(api_key=pinecone_api_key)
    pinecone_index = pc.Index(idx_name)

    vector_store = PineconeVectorStore(
        pinecone_index=pinecone_index,
        add_sparse_vector=True,
    )

    jina_embeddings = JinaEmbedding(api_key=jina_ai_api_key, 
                                    model="jina-embeddings-v3", 
                                    task="retrieval.query",    
                                    embed_batch_size=2, 
                                    dimensions=1024 )

    index = VectorStoreIndex.from_vector_store(vector_store=vector_store, 
                                                embed_model=jina_embeddings) 

    retriever_engine = index.as_retriever(similarity_top_k=10)

    return retriever_engine


def rag_agent_tool(query: str, thought:str =Field(..., description="Analysis of all previous step and detailed reason for selecting current tool/step")):
    """
    This function retrieves information from a vector database according to the query. 
    Information could be a policy docs, FAQs, process to follow to resolve an issue, etc.
    """
    return [output.text for output in get_rag_engine().retrieve(query)]



def past_successful_example(query: str, thought:str =Field(..., description="Analysis of all previous step and detailed reason for selecting current tool/step")):
    """"
    This function is helpful to see how similar query in the past has been handled. This gives hint about how razorypay handles such queries and all applied policies and other information.
    if similar query has been resolved in past then its better to follow the same path.
    """

    results = fd_store.similarity_search_with_score(query, k=5)
    txt = "Below is past similar user query, its resolution and probable company policy derived from it. You need to refer it as hint to figure out if this will be applicable to current query and answer accordingly. Many a times you amy see that for some task support ticket was created and internal team completed the task. but since you might be having access to internal tools, you can now do it which was previously done by internal team. but before doing anything using tools do check policies.\n"

    for i,(res, _) in enumerate(results):
        res.metadata['answer'] = res.metadata['answer'] if res.metadata['answer']==res.metadata['answer'] else ""
        res.metadata['derived_policies_or_process'] = res.metadata['derived_policies_or_process'] if res.metadata['derived_policies_or_process']==res.metadata['derived_policies_or_process'] else ""
        txt+=f"Past user query: {i+1}: " + res.page_content +'\n' + f"Past answer by human support team {i+1}: "+res.metadata['answer'] + '\n' + f"Derived process or policy from this conversation {i+1}: " + res.metadata['derived_policies_or_process'] +'\n\n'
    return txt


def what_human_would_do(query: str, thought:str =Field(..., description="Analysis of all previous step and detailed reason for selecting current tool/step")):
    """"
    This helps in retriving information which is used by internal human support agent as a guideline/hint/process to be able to resolve user queries. An AI agent
    can use this information to understand/plan how to resolve user query. 
    """

    results = knowledge_store.similarity_search_with_score(query, k=2)
    txt = "Below is the probable instruction doc for human agent to follow for resolving user query. You can use this as a guideline to understand what to do for resolving user query.\n"

    for i,(res, _) in enumerate(results):
        txt+=f"Human instruction doc: {i+1}: " + res.page_content +'\n'
    return txt




if __name__ == "__main__":
    out = past_successful_example("how to enable international payments.")
    print(out)
    #out = get_rag_engine().retrieve("how to enable international payments.")
    #print(out[0].keys())
    for o in out:
        print(o.text)
        print("metadata", o.metadata)
        print("***************************************************")
        pass