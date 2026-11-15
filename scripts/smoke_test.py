"""Offline smoke test: run before every push. No API key or network needed.

    python scripts/smoke_test.py

1. builds the database from the files in data/
2. checks the SQL guardrails (raw tables and writes are refused)
3. runs the assistant end to end with a SCRIPTED stand-in model (checks the agent wiring,
   not answer quality; answer quality is measured by assistant/evaluate.py with a real key)
4. loads the Streamlit app headless WITHOUT an API key and fails on any exception
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_core.embeddings import DeterministicFakeEmbedding  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

from assistant import tools as T  # noqa: E402
from assistant.agent import DataAssistant  # noqa: E402
from assistant.retrieval import Retriever  # noqa: E402
from pipeline.build import build  # noqa: E402


class ScriptedModel(BaseChatModel):
    """Replays a fixed list of responses, like a model that calls two tools then answers."""
    script: list = []
    i: int = 0

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kw):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kw):
        msg = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])


def main():
    summary = build(verbose=False)
    assert summary["checks"]["FAIL"] == 0, f"data-quality FAIL checks: {summary['checks']}"

    assert T.run_sql("select count(*) from raw_dld_transactions").error, "raw table must be blocked"
    assert T.run_sql("delete from fct_sales").error, "writes must be blocked"
    assert T.run_sql("select 1; select 2").error, "multiple statements must be blocked"
    assert T.run_sql("select count(*) from fct_sales where is_valid = 1").rows[0][0] > 0

    for retriever in (Retriever(), Retriever(embeddings=DeterministicFakeEmbedding(size=64))):
        assert retriever.search("how is gross yield calculated"), retriever.mode
    assert "vector" in retriever.mode

    script = [
        AIMessage(content="", tool_calls=[{"name": "search_docs", "args": {"query": "gross yield definition"}, "id": "1"}]),
        AIMessage(content="", tool_calls=[{"name": "run_sql", "id": "2", "args": {
            "query": "select area_name, gross_yield from mart_area_unit_kpis where unit_class='Apartment' "
                     "and yield_confidence='Reliable' order by gross_yield desc limit 3"}}]),
        AIMessage(content="Scripted final answer."),
    ]
    ans = DataAssistant(ScriptedModel(script=script)).ask("Top 3 apartment yields?")
    assert ans.error is None and ans.text == "Scripted final answer.", ans
    assert len(ans.sql) == 1 and len(ans.sql[0].rows) == 3 and ans.docs, ans

    # a model that states figures without querying must be caught and the answer withheld
    liar = ScriptedModel(script=[AIMessage(content="Dubai Marina: median price AED 2,100,000, yield 6.7%.")])
    ans = DataAssistant(liar).ask("What will prices be in 2028?")
    assert ans.error and not ans.text and ans.figures_unmatched, "ungrounded figures must be withheld"
    # grounded figures (7.2% from a 0.0719 ratio, rounded AED amounts) must pass
    from assistant.grounding import check_figures
    res = T.run_sql("select gross_yield, median_ready_price_aed, ready_sales_count from mart_area_unit_kpis "
                    "where area_name like '%Jumeirah Village Circle%' and unit_class = 'Apartment'")
    gy, price, n = res.rows[0]
    text = f"Yield is {gy:.1%} on a median ready price of AED {price:,.0f} ({n:,} ready sales, top 3 shown)."
    assert check_figures(text, "JVC yield?", [res], []) == (3, []), check_figures(text, "JVC yield?", [res], [])

    class Boom(ScriptedModel):
        def _generate(self, *a, **k):
            raise RuntimeError("provider down")
    assert DataAssistant(Boom()).ask("anything").error, "provider failure must become a message, not a crash"
    ans = DataAssistant([Boom(), ScriptedModel(script=script)]).ask("Top 3 apartment yields?")
    assert ans.error is None and len(ans.sql) == 1, "must fall back to the next model when one fails"

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300).run()
    assert not at.exception, [e.value for e in at.exception]
    print("smoke test passed:", summary["checks"])


if __name__ == "__main__":
    main()
