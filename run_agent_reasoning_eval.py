# run_agent_reasoning_eval.py
#
# pip install -U openai datasets pandas tqdm
#
# export OPENAI_API_KEY="..."
# python run_agent_reasoning_eval.py
#
# Output:
#   agent_reasoning_results.csv
#   agent_reasoning_summary.csv

import os
import json
import time
import random
import statistics
from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd
from tqdm import tqdm
from datasets import load_dataset
from openai import OpenAI


# ============================================================
# Config
# ============================================================

MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")

EFFORTS = ["none", "low", "medium"]

N_TOOL = 25
N_REACT = 25
N_VERIFY = 25
N_PLAN = 25

MAX_STEPS = 6
SEED = 42

random.seed(SEED)

client = OpenAI()


# ============================================================
# Data structure
# ============================================================

@dataclass
class Episode:
    id: str
    task_type: str
    question: str
    answer: str
    meta: dict


# ============================================================
# Local deterministic tools
# ============================================================

KB = {
    "alice_city": "Seoul",
    "bob_city": "Tokyo",
    "carol_city": "Paris",

    "Seoul_country": "South Korea",
    "Tokyo_country": "Japan",
    "Paris_country": "France",

    "South Korea_currency": "KRW",
    "Japan_currency": "JPY",
    "France_currency": "EUR",

    "South Korea_capital": "Seoul",
    "Japan_capital": "Tokyo",
    "France_capital": "Paris",

    "Seoul_population": "9500000",
    "Tokyo_population": "14000000",
    "Paris_population": "2100000",
}


def lookup(key: str):
    return KB.get(key, "NOT_FOUND")


def calculator(expression: str):
    """
    Restricted arithmetic evaluator for benchmark purposes.
    """
    allowed = set("0123456789+-*/(). %")
    if not set(expression) <= allowed:
        return "ERROR"

    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception:
        return "ERROR"


def verify(expected: str, actual: str):
    return {
        "valid": str(expected).strip().lower()
        == str(actual).strip().lower()
    }


TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "lookup",
        "description": "Retrieve one fact from the local knowledge base.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string"
                }
            },
            "required": ["key"],
            "additionalProperties": False
        },
    },
    {
        "type": "function",
        "name": "calculator",
        "description": "Evaluate a basic arithmetic expression.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string"
                }
            },
            "required": ["expression"],
            "additionalProperties": False
        },
    },
    {
        "type": "function",
        "name": "verify",
        "description": "Verify whether an expected value matches an actual value.",
        "parameters": {
            "type": "object",
            "properties": {
                "expected": {"type": "string"},
                "actual": {"type": "string"},
            },
            "required": ["expected", "actual"],
            "additionalProperties": False
        },
    },
]


def execute_tool(name, args):
    if name == "lookup":
        return lookup(**args)

    if name == "calculator":
        return calculator(**args)

    if name == "verify":
        return verify(**args)

    return "UNKNOWN_TOOL"


# ============================================================
# 1. Tool-selection dataset
# ============================================================

def make_tool_tasks(n=25):
    templates = []

    arithmetic = [
        ("What is 137 * 42?", "5754", "calculator"),
        ("Compute 971 + 388.", "1359", "calculator"),
        ("What is 144 / 12?", "12.0", "calculator"),
        ("Calculate (18 + 7) * 4.", "100", "calculator"),
        ("Compute 900 - 347.", "553", "calculator"),
    ]

    lookups = [
        ("Where does Alice live?", "Seoul", "lookup"),
        ("Where does Bob live?", "Tokyo", "lookup"),
        ("Which country is Seoul in?", "South Korea", "lookup"),
        ("What currency does Japan use?", "JPY", "lookup"),
        ("What is the population of Paris?", "2100000", "lookup"),
    ]

    for q, a, tool in arithmetic + lookups:
        templates.append(
            Episode(
                id="",
                task_type="tool",
                question=q,
                answer=a,
                meta={"expected_tool": tool},
            )
        )

    out = []

    for i in range(n):
        base = templates[i % len(templates)]

        out.append(
            Episode(
                id=f"tool_{i}",
                task_type="tool",
                question=base.question,
                answer=base.answer,
                meta=base.meta.copy(),
            )
        )

    return out


# ============================================================
# 2. ReAct / multi-hop
# ============================================================

def make_react_tasks(n=25):

    chains = [
        (
            "What currency is used in the country where Alice lives?",
            "KRW",
            [
                "alice_city",
                "Seoul_country",
                "South Korea_currency",
            ],
        ),

        (
            "What currency is used in the country where Bob lives?",
            "JPY",
            [
                "bob_city",
                "Tokyo_country",
                "Japan_currency",
            ],
        ),

        (
            "What is the capital of the country where Carol lives?",
            "Paris",
            [
                "carol_city",
                "Paris_country",
                "France_capital",
            ],
        ),

        (
            "What is the population of the city where Alice lives?",
            "9500000",
            [
                "alice_city",
                "Seoul_population",
            ],
        ),

        (
            "What country does the city where Bob lives belong to?",
            "Japan",
            [
                "bob_city",
                "Tokyo_country",
            ],
        ),
    ]

    out = []

    for i in range(n):
        q, a, chain = chains[i % len(chains)]

        out.append(
            Episode(
                id=f"react_{i}",
                task_type="react",
                question=q,
                answer=a,
                meta={"gold_keys": chain},
            )
        )

    return out


# ============================================================
# 3. Verification / error recovery
# ============================================================

def make_verify_tasks(n=25):

    pairs = [
        ("137 * 42", "5754"),
        ("83 * 17", "1411"),
        ("992 - 418", "574"),
        ("144 / 12", "12.0"),
        ("(23 + 12) * 3", "105"),
    ]

    out = []

    for i in range(n):

        expr, correct = pairs[i % len(pairs)]

        # deliberately inject wrong observation
        wrong = str(float(correct) + 1)

        prompt = f"""
A previous calculator returned this result:

Expression: {expr}
Result: {wrong}

Check whether the result is correct.
If incorrect, call tools and recover the correct value.
"""

        out.append(
            Episode(
                id=f"verify_{i}",
                task_type="verify",
                question=prompt.strip(),
                answer=correct,
                meta={
                    "expression": expr,
                    "bad_result": wrong,
                },
            )
        )

    return out


# ============================================================
# 4. Planning / composition
# ============================================================

def make_plan_tasks(n=25):

    templates = [
        (
            """
Alice lives in a city.
Find the population of Alice's city and divide it by 1000.
""",
            "9500.0",
        ),

        (
            """
Bob lives in a city.
Find the population of Bob's city and divide it by 1,000,000.
""",
            "14.0",
        ),

        (
            """
Find the populations of Seoul and Paris, then calculate
the difference between them.
""",
            "7400000",
        ),

        (
            """
Find Tokyo's population and divide it by Paris's population.
""",
            str(14000000 / 2100000),
        ),

        (
            """
Find Seoul's population and Tokyo's population.
Return their sum.
""",
            "23500000",
        ),
    ]

    out = []

    for i in range(n):

        q, a = templates[i % len(templates)]

        out.append(
            Episode(
                id=f"plan_{i}",
                task_type="plan",
                question=q.strip(),
                answer=a,
                meta={},
            )
        )

    return out


# ============================================================
# Optional open-source HotpotQA questions
# ============================================================

def load_hotpot_examples(limit=10):
    """
    Optional source of natural multi-hop wording.

    We DO NOT directly score Hotpot answer generation here.
    These can later replace synthetic questions while still
    using deterministic local tools.
    """

    try:
        ds = load_dataset(
            "hotpot_qa",
            "distractor",
            split=f"validation[:{limit}]",
            trust_remote_code=True,
        )

        return [
            {
                "question": x["question"],
                "answer": x["answer"],
            }
            for x in ds
        ]

    except Exception as e:
        print("HotpotQA loading skipped:", e)
        return []


# ============================================================
# Responses API agent loop
# ============================================================

SYSTEM_PROMPT = """
You are an agent solving benchmark tasks.

Use tools whenever necessary.

Rules:
- Prefer the minimum number of tool calls.
- Do not guess values available through tools.
- For multi-step questions, use observations from previous tools.
- If given a potentially incorrect result, verify and correct it.
- Return only the final answer once you are confident.
"""


def reasoning_config(effort):
    return {
        "effort": effort
    }


def run_episode(ep: Episode, effort: str):

    start = time.perf_counter()

    response = client.responses.create(
        model=MODEL,
        instructions=SYSTEM_PROMPT,
        input=ep.question,
        tools=TOOL_SCHEMAS,
        reasoning=reasoning_config(effort),
    )

    tool_calls = 0
    used_tools = []
    lookup_keys = []

    for step in range(MAX_STEPS):

        calls = [
            x
            for x in response.output
            if x.type == "function_call"
        ]

        if not calls:
            break

        outputs = []

        for call in calls:

            tool_calls += 1
            used_tools.append(call.name)

            try:
                args = json.loads(call.arguments)
            except Exception:
                args = {}

            if call.name == "lookup":
                lookup_keys.append(args.get("key"))

            result = execute_tool(
                call.name,
                args,
            )

            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result),
                }
            )

        response = client.responses.create(
            model=MODEL,
            previous_response_id=response.id,
            input=outputs,
            tools=TOOL_SCHEMAS,
            reasoning=reasoning_config(effort),
        )

    latency = time.perf_counter() - start

    final_answer = response.output_text.strip()

    usage = response.usage

    reasoning_tokens = 0

    try:
        reasoning_tokens = (
            usage.output_tokens_details.reasoning_tokens or 0
        )
    except Exception:
        pass

    return {
        "prediction": final_answer,
        "latency_sec": latency,
        "tool_calls": tool_calls,
        "used_tools": used_tools,
        "lookup_keys": lookup_keys,
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "reasoning_tokens": reasoning_tokens,
    }


# ============================================================
# Metrics
# ============================================================

def normalize(x):
    return (
        str(x)
        .strip()
        .lower()
        .replace(",", "")
    )


def numeric_equal(a, b, tol=1e-5):

    try:
        return abs(float(a) - float(b)) <= tol
    except Exception:
        return False


def answer_match(pred, gold):

    p = normalize(pred)
    g = normalize(gold)

    if p == g:
        return True

    if numeric_equal(p, g):
        return True

    # tolerate answers such as:
    # "The answer is 5754"
    if g in p and len(g) >= 3:
        return True

    return False


def score_episode(ep, result):

    score = {
        "success": int(
            answer_match(
                result["prediction"],
                ep.answer,
            )
        )
    }

    # exact tool selection
    if ep.task_type == "tool":

        expected = ep.meta["expected_tool"]

        score["tool_correct"] = int(
            len(result["used_tools"]) > 0
            and result["used_tools"][0] == expected
        )

    else:
        score["tool_correct"] = None

    # ReAct trajectory score
    if ep.task_type == "react":

        gold = ep.meta["gold_keys"]

        observed = [
            x for x in result["lookup_keys"]
            if x is not None
        ]

        gold_found = sum(
            1 for x in gold if x in observed
        )

        score["trajectory_recall"] = (
            gold_found / len(gold)
        )

    else:
        score["trajectory_recall"] = None

    # Did verification recover from injected error?
    if ep.task_type == "verify":

        score["recovered"] = score["success"]

    else:
        score["recovered"] = None

    return score


# ============================================================
# Run benchmark
# ============================================================

def main():

    episodes = (
        make_tool_tasks(N_TOOL)
        + make_react_tasks(N_REACT)
        + make_verify_tasks(N_VERIFY)
        + make_plan_tasks(N_PLAN)
    )

    assert len(episodes) == 100

    print("=" * 70)
    print("Agent reasoning benchmark")
    print("=" * 70)

    print("model:", MODEL)
    print("episodes:", len(episodes))
    print("efforts:", EFFORTS)

    rows = []

    for effort in EFFORTS:

        print("\nEFFORT:", effort)

        for ep in tqdm(episodes):

            try:

                result = run_episode(
                    ep,
                    effort,
                )

                score = score_episode(
                    ep,
                    result,
                )

                row = {
                    "id": ep.id,
                    "task_type": ep.task_type,
                    "effort": effort,
                    "question": ep.question,
                    "gold": ep.answer,
                    **result,
                    **score,
                }

            except Exception as e:

                row = {
                    "id": ep.id,
                    "task_type": ep.task_type,
                    "effort": effort,
                    "question": ep.question,
                    "gold": ep.answer,
                    "prediction": "",
                    "latency_sec": None,
                    "tool_calls": None,
                    "used_tools": [],
                    "lookup_keys": [],
                    "input_tokens": None,
                    "output_tokens": None,
                    "reasoning_tokens": None,
                    "success": 0,
                    "tool_correct": None,
                    "trajectory_recall": None,
                    "recovered": None,
                    "error": str(e),
                }

            rows.append(row)

    df = pd.DataFrame(rows)

    df.to_csv(
        "agent_reasoning_results.csv",
        index=False,
    )

    # ========================================================
    # Summary
    # ========================================================

    summary = (
        df
        .groupby(
            ["task_type", "effort"],
            as_index=False
        )
        .agg(
            n=("id", "count"),
            success=("success", "mean"),
            latency_sec=("latency_sec", "mean"),
            tool_calls=("tool_calls", "mean"),
            reasoning_tokens=("reasoning_tokens", "mean"),
            output_tokens=("output_tokens", "mean"),
            tool_accuracy=("tool_correct", "mean"),
            trajectory_recall=("trajectory_recall", "mean"),
            recovery_rate=("recovered", "mean"),
        )
    )

    summary.to_csv(
        "agent_reasoning_summary.csv",
        index=False,
    )

    print("\n")
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)

    print(
        summary.to_string(
            index=False,
            float_format=lambda x: f"{x:.3f}"
        )
    )

    print("\nSaved:")
    print("  agent_reasoning_results.csv")
    print("  agent_reasoning_summary.csv")


if __name__ == "__main__":
    main()
