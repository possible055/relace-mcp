# LocAgent / Loc-Bench 方法論調查與 fast_search 資料集設計報告

（繁體中文說明；技術名詞維持 English）

## 0. 目標

你想用 LocAgent / Loc-Bench（ACL 2025）的方法論，建立「符合研究標準」的 dataset 來測試 `fast_search`。

本報告做三件事：
1) 整理 LocAgent 論文的完整做法（graph representation、tool interface、agent workflow、fine-tuning、benchmark、metrics）。
2) 用 GitHub API 逐檔查看 `gersteinlab/LocAgent` 的實作，對照論文描述到可以落地重現。
3) 把 LocAgent 風格的 dataset 設計映射到 `relace-mcp` 的 `fast_search` 評估框架（本 repo 已有 `benchmark/` pipeline）。

參考來源：
- Paper (ACL Anthology): https://aclanthology.org/2025.acl-long.426/
- Paper (arXiv HTML v2): https://arxiv.org/html/2503.09089v2
- GitHub: https://github.com/gersteinlab/LocAgent
- Loc-Bench_V1 (HF): https://huggingface.co/datasets/czlll/Loc-Bench_V1

---

## 1. LocAgent 論文方法論（重點到可復現）

### 1.1 Task 定義：Code Localization

- Input：自然語言問題描述（常見來源是 GitHub issue / PR 描述）。
- Output：定位「需要修改」的 code location（論文同時評估 file / module / function 級別）。
- 核心挑戰：NL ↔ code elements 的橋接，且常需要跨多個 dependency 的 multi-hop reasoning。

### 1.2 Graph-based Code Representation（Section 3.1）

LocAgent 的中介表示是 directed heterogeneous graph。

- Node types `A = {directory, file, class, function}`
- Edge types `R = {contain, import, invoke, inherit}`

論文對 Python repos 的構建流程（關鍵設計）：
- 先把所有 directory 與 `.py` file 作為 nodes。
- 對每個 `.py` 用 AST 解析，遞迴把 class / function（含 inner function）加入 nodes。
- 以 function 為最小粒度 node，並用 function 的 code content 作為 retrieval document（控制資訊密度以符合 LLM context window）。
- 用 `contain` 把 directory→file→class→function 串成 tree，提供類 IDE 的「層級導航」。
- 再補上跨層級 dependency edges：
  - `invoke`: function/class → function/class（class instantiation 也算 invoke）
  - `import`: file → function/class
  - `inherit`: class → class

### 1.3 Sparse Hierarchical Entity Indexing（Section 3.1）

論文的 indexing 是「hierarchical」而且「sparse」，目標是讓 `SearchEntity` 既快又不吃 token。

索引結構（從上到下）：
1) Entity ID index：每個 node 用 fully qualified name 當唯一 ID。
   - 例：`src/utils.py:MathUtils.calculate_sum`
2) Global name dictionary：把簡名（例如 `calculate_sum`）對映到所有同名 entities。
3) Inverted index over entity IDs：用 BM25 處理 keyword 與 entity name/ID 不完全一致的情境。
4) Inverted index over code chunks：當 keyword 根本不在 entity ID（例如 global variable）時，靠 code chunk 反查 entity。

這段對 dataset 的啟示：
- 只看 directory 結構不夠，因為 module dependencies 會「跨資料夾」。
- 想評估 multi-hop，最好能標註 query anchors（提到的 entity）到 GT 的 graph distance（論文後面用 Hop N 分析）。

### 1.4 Unified Tools（Section 3.2）

論文把 codebase exploration 的所有操作收斂成三個 tools（Table 2）：

1) `SearchEntity(keywords) -> related entities + code snippets`
- 透過 hierarchical index 先 exact match，再 fallback 到 fuzzy/BM25。
- 重要：輸出設計避免「超長 context」。

2) `TraverseGraph(start_entities, direction, traverse_hops, entity_types, relation_types) -> subgraph`
- type-aware BFS。
- 可控制 direction / hops。
- 允許 model 選 entity_types + relation_types，相當於讓 LLM 用 coding knowledge 生成 meta-path（heterogeneous graph analysis 的關鍵）。
- 輸出用「expanded tree-based format」呈現 subgraph（見 1.5）。

3) `RetrieveEntity(entity_ids) -> full attributes/code`
- 回傳 file path、line number、code content 等。

### 1.5 Tool Output Design（Appendix A.1）

#### A.1.1 SearchEntity 的多層級輸出

論文描述 SearchEntity 用多 granular formats 來控制 token：`fold`, `preview`, `full code`（文字段落中提到「四種」，但該段明確列出的名稱為這三種）。

直覺對應：
- `fold`：只給 entity ID/type（最低 token）。
- `preview`：給摘要或 skeleton /短片段。
- `full code`：給完整 code。

#### A.1.2 TraverseGraph 的 tree-based subgraph output

論文明確指出：graph formatting 會強烈影響 LLM graph reasoning。

tree-based format 的設計特徵（論文列出的三點）：
1) 把 subgraph 展成 tree，用 indentation 讓 LLM 感知距離（node distance from root）。
2) 每個 node 顯示完整 entity ID（例如 `django/core/validators.py:RegexValidator`）。
3) edge 顯示 relation types，包含 reversed relations（upstream 方向）。

論文也比較多種輸出格式（Table 9 提及）：`row`, `incident`, `Graphviz DOT`, `JSON`, `tree-based (Ours)`；結論是「tree 展開（JSON/tree-based）」顯著提升，且 tree-based 最好。

### 1.6 Agent Workflow（Section 3.2）

LocAgent 用 CoT prompting（Appendix D）引導 agent 逐步做 localization。

工作流程（論文明確列 4 步）：
1) Keyword extraction：把 issue statement 分類後抽出 keywords。
2) Linking keywords to code entities：呼叫 `SearchEntity` 把 keyword 對到 entities。
3) Generate the logical flow from fault to failure：
   - 先找 entry points。
   - 迭代呼叫 `TraverseGraph`/`RetrieveEntity`/`SearchEntity` 探索。
   - 組出 fault→failure 的 logic flow。
4) Locate the target entities：依 logic flow 找需要修改的 entities，並排序。

Confidence Estimation（Consistency-based）：
- 用 Reciprocal Rank 當每次 iteration 的初始 confidence。
- 跨 iterations 聚合成 final confidence。
- 直覺：模型若多次一致把某位置排前面，可信度更高。

### 1.7 Open-source Model Fine-tuning（Section 3.3）

- 為了降低 proprietary LLM API cost 與 data security concern，作者 fine-tune open-source models。
- 訓練資料：433 條 Claude-3.5 成功 trajectories（SWE-bench training set，且「成功」定義是 localization 正確）。
- 另 sample 335 條初版 Qwen2.5-32B 生成、且成功的 trajectories，做 self-improvement loop。
- 再用整體 dataset distill 到 7B。
- 方法：SFT + LoRA。

### 1.8 Loc-Bench：Dataset Construction（Section 4）

動機（4.1）：
- SWE-Bench(-Lite) 有 contamination 風險。
- 任務設計不是為 localization。
- 類別嚴重不均衡（SWE-Bench-Lite 幾乎都是 bug report）。

Loc-Bench（4.2）做法：
- 收集 Python repos 的 up-to-date issues（降低 pre-training bias）。
- 類別更完整：bug / feature / security / performance。
- 對 bug report：收集 October 2024 之後建立的 GitHub issues（晚於多數現代 LLM release）。
- 對 security / performance：用 GitHub Search API + keywords（例：「latency improvement」）補足樣本。
- 篩選限制：排除 patch 修改 >5 個 Python files 或 >10 個 functions 的案例。

論文 Table 3 的分佈（Loc-Bench total=560）：
- Bug Report: 242
- Feature Request: 150
- Security Issue: 29
- Performance Issue: 139

### 1.9 評估指標（Section 5.1）

- 主要指標：`Acc@k`（受 Agentless 啟發）。
- 成功條件：top-k predictions 內必須包含「所有 relevant locations」。
- 報告：file Acc@1/3/5；function Acc@5/10。
- module 評估更寬鬆：只要找到 patched class 裡任一 function。

---

## 2. GitHub `gersteinlab/LocAgent` 實作調查（對照論文）

### 2.1 Repo 結構（GitHub Contents API）

根目錄主要項目：
- `dependency_graph/`：graph construction + traversal
- `plugins/location_tools/`：agent tools
- `repo_index/`：indexing（含 embedding / faiss 等）
- `evaluation/`：metrics + notebook
- `auto_search_main.py`：主程式（localize/merge）
- `build_bm25_index.py`：BM25 index 批次建置
- `sft_train.py`：SFT training

### 2.2 Graph Construction（`dependency_graph/build_graph.py`）

實作上用的 node/edge 名稱（注意 plural）：
- Node types：`directory`, `file`, `class`, `function`
- Edge types：`contains`, `imports`, `invokes`, `inherits`

關鍵實作點：
- 用 Python `ast` 解析 file，抽 class/function nodes。
- `contains` 建出 directory→file→class→function 的 tree。
- `find_imports` 支援 `import` 與 `from ... import ...`，並嘗試 resolve module path。
- `imports` edges：把 file 或 entity 指到 import 進來的 module/file/entity。
- `invokes` / `inherits`：從 AST 中抓 call / base class，並在 graph 中用 fuzzy/global 名稱對齊（`global_import` 相關）。
- graph backend：`networkx.MultiDiGraph`。

### 2.3 Graph Traversal 與 tree-based output（`dependency_graph/traverse_graph.py`）

`traverse_tree_structure` 的輸出特徵：
- 用 `├──` / `└──` + indentation 畫 tree。
- 每條邊輸出 `edge_type ── node_id`。
- upstream 的邊會把 edge type 改成 `etype + '-by'`（對應論文的 reversed relations）。
- 支援 `direction in {'downstream','upstream','both'}` 與 `hops`（`-1` 會被設成上限 20）。
- 支援 `node_type_filter` / `edge_type_filter`。

這基本上就是論文 Appendix A.1.2 描述的 tree-based subgraph format。

### 2.4 Tool APIs（`plugins/location_tools/repo_ops/repo_ops.py`）

實作對外 export 的 tools（`__all__`）：
- `search_code_snippets`
- `explore_graph_structure`
- `explore_tree_structure`

這三個對應到論文的抽象：
- `search_code_snippets` ≈ `SearchEntity` +（部分）`RetrieveEntity`
- `explore_tree_structure` / `explore_graph_structure` ≈ `TraverseGraph`

#### 2.4.1 `search_code_snippets`

功能整合：
- 可以用 `search_terms` 找 entity（file / class / function）或做 keyword search。
- 可以用 `line_nums` + `file_path_or_pattern` 取特定行附近的 code snippet。
- 支援 `file_path_or_pattern`（glob）限制搜尋範圍。

輸出模式（見 `plugins/location_tools/utils/result_format.py`）：
- `complete`：回傳完整 code content。
- `preview`：class/file >100 lines 時回傳 skeleton + hint。
- `code_snippet`：回傳指定 range 的 snippet。
- `fold`：只回傳 type + entity ID。

這對應論文「控制 context 長度」的 tool output design。

#### 2.4.2 `explore_tree_structure`

參數與論文幾乎一樣：
- `start_entities: List[str]`
- `direction: 'downstream'|'upstream'|'both'`
- `traversal_depth`（hops，`-1` 表示 unlimited 但會 cap）
- `entity_type_filter`（node types）
- `dependency_type_filter`（edge types）

另外：
- `_validate_graph_explorer_inputs` 會在 entity 無效時用 BM25 給 candidate entities 當 hints。

### 2.5 批次 Indexing 與環境變數

README 建議先 batch build index：
- `python dependency_graph/batch_build_graph.py --dataset 'czlll/Loc-Bench_V1' --split 'test' --num_processes 50 --download_repo`

BM25 index：
- `python build_bm25_index.py --dataset ... --download_repo`

執行前需設：
- `GRAPH_INDEX_DIR`
- `BM25_INDEX_DIR`

在 `plugins/location_tools/utils/util.py` 直接 `assert GRAPH_INDEX_DIR != ''` 與 `assert BM25_INDEX_DIR != ''`。

### 2.6 Localization pipeline 與輸出格式

`auto_search_main.py` 會輸出 JSONL：
- `instance_id`
- `found_files`, `found_modules`, `found_entities`
- `raw_output_loc`
- `meta_data: {repo, base_commit, problem_statement, patch}`

### 2.7 Evaluation（`evaluation/eval_metric.py`）

`evaluate_results(loc_file, level2key_dict, ...)`：
- 會用 `datasets.load_dataset(dataset, split=...)` 讀 benchmark。
- GT 主要從 `edit_functions` 推導：
  - file-level：取 `edit_functions` 的 file path。
  - module-level：取 `file:ClassName`（用 `split('.')[0]` 取 module/class）。
  - function-level：取 `file:QualifiedName`（並把 `.__init__` 特判）。
- 支援 metrics：`acc`, `ndcg`, `precision`, `recall`, `map`。

這部分提供了「除了 Acc@k 之外」更完整的 IR-style 指標。

---

## 3. `czlll/Loc-Bench_V1` dataset 格式觀察

使用 HuggingFace datasets-server 取樣（不需額外安裝套件）後，`Loc-Bench_V1` row 具有：
- `repo`, `instance_id`, `base_commit`
- `patch`, `test_patch`
- `problem_statement`, `hints_text`
- `created_at`
- `labels`（GitHub labels；不是 localization GT）
- `category`（Bug Report / Feature Request / Security Vulnerability / Performance Issue）
- `edit_functions`（function-level GT 的主要來源）
- `added_functions`

重要結論：
- Loc-Bench 的 localization GT 其實主要在 `edit_functions`（以及可能的 `added_functions`），不是 `labels`。
- `edit_functions` 的字串格式是 `path/to/file.py:QualifiedName`（例如 `backend/chainlit/socket.py:connect`）。

---

## 4. 把 LocAgent 方法論映射到 `relace-mcp` 的 `fast_search` dataset 設計

### 4.1 先釐清：本 repo 已有 fast_search benchmark pipeline

`relace-mcp` 其實已經內建一套「用 dataset 跑 `fast_search` 並算 localization metrics」的 pipeline：
- Dataset schema：`benchmark/schemas.py` 的 `DatasetCase`（支援 `hard_gt` 與 `soft_context`）
- Dataset loader：`benchmark/datasets/mulocbench.py`
- Runner：`benchmark/runner/executor.py` 的 `BenchmarkRunner`
  - 會 checkout `case.repo` 到 `case.base_commit`
  - 執行 `FastAgenticSearchHarness` 或 `DualChannelHarness`
  - 讀 `result['files']`（path -> [[start,end], ...]）
  - 計算 file recall/precision、line coverage/precision、function hit 等
- CLI：`python -m benchmark.cli.run --help`

也就是說：你要做的「用研究標準 dataset 測試 `fast_search`」其實只差 dataset 的品質與可分析欄位。

### 4.2 LocAgent 風格 dataset 的最小落地版本（相容現有 schema）

建議先做到「不改 code 就能跑」：
- dataset 檔維持 `DatasetCase` 需要的欄位：
  - `id`, `query`, `repo`, `base_commit`, `hard_gt`（至少 1 筆）
  - 可選：`soft_context`, `issue_url`, `pr_url`, `solvability`

你可以額外塞 LocAgent-style 欄位（loader 會忽略未知欄位）：
- `category`: Bug/Feature/Security/Performance
- `query_entities`: query anchors（見 4.3）
- `localization_path`: graph path（見 4.3）
- `hop_n`: multi-hop 難度指標

這樣可以先用現有 runner 跑 `fast_search`，同時保留研究分析需要的附加標註。

### 4.3 LocAgent-style 擴充欄位建議（Query Anchors + Localization Path）

以下是一個建議的 JSONL schema（在 `DatasetCase` 之外加欄位）：

```json
{
  "id": "...",
  "query": "...",
  "repo": "org/name",
  "base_commit": "...",

  "category": "Bug|Feature|Security|Performance",

  "hard_gt": [
    {
      "path": "src/foo.py",
      "function": "MyClass.my_method",
      "range": [120, 180],
      "target_ranges": [[150, 155]],
      "class": "MyClass",
      "signature": "def my_method(...):"
    }
  ],

  "query_entities": [
    {
      "mention": "FastAgenticSearchHarness",
      "node_type": "class",
      "resolved": {
        "path": "src/relace_mcp/tools/search/harness/core.py",
        "line": 158
      },
      "confidence": 0.9
    }
  ],

  "localization_path": [
    {
      "from": {"path": "...", "node": "...", "node_type": "class"},
      "relation": "imports|invokes|contains|inherits",
      "direction": "downstream|upstream",
      "to": {"path": "...", "node": "...", "node_type": "function"}
    }
  ],

  "hop_n": 2,
  "issue_url": "...",
  "pr_url": "..."
}
```

設計原則（對齊 LocAgent）：
- `query_entities` 只記「query 中真的出現的 mentions」，避免事後補。這是 Query Grounding 的 GT。
- `localization_path` 不是唯一答案，可以允許多條（multi-path），但至少要有一條最短或最合理的 path。
- `hop_n` 用 graph shortest path（或近似）量化 difficulty。

### 4.4 如何產生 `query_entities`（研究標準做法）

建議流程（從自動到人工 QA）：
1) 規則抽取：從 query 取出 backticks、CamelCase、snake_case、file path pattern。
2) 候選對齊：
   - 在 repo snapshot 建立 entity index（可復用 `benchmark/analysis/call_graph.py` 的 global index，或直接借鑑 LocAgent 的 entity ID 格式）。
   - 用 exact match + fuzzy match（BM25/substring）找候選。
3) 人工確認：確保 mention → node 的對齊正確。

### 4.5 如何產生 `localization_path` 與 `hop_n`

如果要完全對齊 LocAgent，graph 應包含：
- `contains`（目錄/檔案/類別/函數層級）
- `imports`（Python import）
- `invokes`（call graph）
- `inherits`（class inheritance）

在 `relace-mcp` 內，已經有可用的 building blocks：
- `benchmark/analysis/call_graph.py`：tree-sitter 抽取 function calls（可形成 `invokes`）
- `benchmark/analysis/ast_spans.py`：把範圍 normalize 到 AST boundaries（利於 function-level GT）

最小可行方案：
- 先只用 `invokes`（call graph）來算 `hop_n`，做一版「multi-hop difficulty」。
- 進階再補 `imports` / `inherits`。

### 4.6 評估維度（對應 LocAgent 與 fast_search）

#### 4.6.1 fast_search 既有指標（本 repo 直接支援）
- File-level：precision / recall
- Range-level：line coverage / precision_matched
- Function-level：function hit rate

#### 4.6.2 LocAgent-style 擴充指標（需要你在 pipeline 額外計算）
- Query Grounding Accuracy：`query_entities` 是否正確對齊（可用 rule 或人工標註當 GT）。
- Path Accuracy：`localization_path` 是否存在一條合理 path（或 shortest path）連到 `hard_gt`。
- Difficulty stratification：按 `hop_n` 分 bucket，分層報告 `fast_search` 的 recall/coverage。

### 4.7 建議的 dataset 建置規格（研究標準 check list）

- Contamination control：
  - 優先選 recent issues（Loc-Bench 的做法是 October 2024 之後）。
  - 在報告中記錄 issue created_at / PR merged_at（如果你要公開 dataset）。
- 多樣性：Bug/Feature/Security/Performance 分佈要可控。
- 規模限制：參考 Loc-Bench，限制 modified files 與 functions 數量（避免 GT 太分散）。
- 可復現：每筆 case 必須能用 `base_commit` checkout。
- 不洩漏：query 盡量避免直接出現 target file path（除非你要測「明確定位」子任務）。

### 4.8 在 `relace-mcp` 內跑 benchmark（驗證 dataset 是否可用）

用本 repo 內建 CLI（`--dataset` 若不是 absolute path，會以 `benchmark/` 為基準解析）：

```bash
uv run -- bash -lc "python -m benchmark.cli.build_locbench --output artifacts/data/raw/locbench_v1.jsonl"

uv run -- bash -lc "python -m benchmark.cli.run --dataset artifacts/data/processed/elite_50.jsonl --limit 10 --harness dual"

uv run -- bash -lc "python -m benchmark.cli.run --dataset artifacts/data/raw/locbench_v1.jsonl --limit 10 --harness dual"
```

（你也可以切 `--harness fast` 直接測 single-harness。）

---

## 5. 結論：你應該怎麼做（最短路徑）

1) 先用現有 `DatasetCase` schema 做出可跑的 dataset（至少 100~500 cases），用 `benchmark.cli.run` 跑起來，確保 metrics pipeline 穩。
2) 再把 LocAgent-style 的 `query_entities` / `localization_path` / `hop_n` 加回 dataset（不必先改 code），用它做分層分析（multi-hop difficulty）。
3) 若你要「研究發表等級」：再把這些欄位正式納入 schema，補上 Query Grounding / Path Accuracy 的 evaluator。

（如果你下一步要我幫你：我可以直接在 `docs/` 寫一份 dataset schema + annotation guideline 的更精細版本，或幫你加上 `query_entities`/`hop_n` 的自動產生腳本。）
