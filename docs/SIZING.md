# Which machine to buy — a team of two

Costed on prices surveyed **2026-10-19**, with the reasoning and the command
that reproduces every number.

> Every figure comes from `ai-bunker recommend`. Nothing here is a quote, and
> nothing is a guess either: the model is a memory roofline validated against
> published measurements, the prices are observed listings, and both are shown
> so you can disagree with either.

**The notation, once, because the rest of this document is made of it.** A
**GPU** is a graphics processing unit, the chip or card a model's weights are
read from, and **VRAM** is its video random-access memory — on a discrete card,
all the room a model has. An **LLM** is a large language model. **B** counts
billions of parameters, so a *24B* model carries 24 billion weights. **bf16**,
**FP8**, **Q4** and **AWQ4** say how many bits each of those weights is stored
on: bf16 is the 16-bit *brain floating point* format models are trained in, FP8
is 8-bit floating point, Q4 a 4-bit quantisation, and AWQ4 *activation-aware
weight quantisation* at 4 bits. **GB** is gigabytes; **GiB** gibibytes and
**KiB** kibibytes, the powers-of-two kind, 2³⁰ and 2¹⁰ bytes apiece. **tok/s**
is tokens per second. And the **KV cache** is the key–value cache, what a model
keeps about the tokens already in a conversation — it grows with the context
and is re-read for every token generated.

**The short answer.** Don't buy yet. Run the model on the Mac you already own
and measure it — the arithmetic says it already clears the bar. If it does, the
cheapest real upgrade is a **$5,600 Mac Studio**, not a $12,600 GPU. The GPU
only becomes necessary if you need the vision model with reliable structured
output, which Apple's serving stack cannot give you today.

---

## 0. The one fact that decides everything

Generating a token requires reading every **active** weight out of memory once.
So the ceiling on speed is neither compute nor capacity:

```
tokens/second  ≤  memory bandwidth  /  active weight bytes
```

Published DGX Spark measurements confirm it almost exactly. The GB10 has
273 GB/s: Qwen3 8B at bf16 (~16 GB) is measured at **13.6 tok/s** against a
roofline of 17.1, and Llama 3.1 70B at Q4 (~40 GB) at **4.4 tok/s** against 6.8.
The model used here assumes 70% efficiency, conservative against both.

### The word that does the work is *active*

For a dense model, active weights are the whole checkpoint. For a **mixture of
experts**, they are a fraction of it — and that fraction moves the wall by
almost an order of magnitude.

| Model | Total | Active per token | Implied ceiling at 819 GB/s |
|---|---:|---:|---:|
| Devstral Small 2 24B, dense, FP8 | 25 GiB | 25 GiB | ~23 tok/s |
| Qwen3-Coder-Next 80B/3B MoE, AWQ4 | 45 GiB | ~9 GiB¹ | ~62 tok/s |

¹ The catalogue floors MoE active weights at 20% of the checkpoint rather than
the nominal 3.75%. Batching widens the set of experts touched per step, so the
true read sits between the two; the floor keeps a large batch from being
credited with single-stream economics.

**This is the whole finding.** The best open coding model available
(Qwen3-Coder-Next, 70.6 on SWE-bench Verified, a software engineering
benchmark) is also the *fastest* to serve, and
it is nearly three times faster than the safe 24B dense choice on the same
hardware. Choosing a smaller model to go faster is, here, exactly backwards.

### Why 20 tok/s

A coding agent does not emit a sentence, it emits a patch. At 20 tok/s a
1,500-token edit lands in 75 seconds, which is tolerable. At 6 tok/s it takes
four minutes, the human switches tabs, and the tool is abandoned inside a week.
Raise the floor with `--comfort-tps` and watch everything get more expensive.

### How many sequences two people need

Not `2 × duty_cycle`. An average is the wrong statistic for a capacity
question. Each person is modelled as independently decoding with probability
`duty_cycle × simultaneity` = 12.5%, sized at the 95th percentile of that
binomial — and small teams get a **floor of two concurrent sequences**
regardless, because below a handful of people the averaging that makes a
percentile meaningful does not happen. The failure the floor prevents is the
obvious one: one colleague's long generation blocking the other's entirely.

**Two people need two concurrent sequences above 20 tok/s.** That is a low bar,
and it is why this sizing is not about concurrency at all.

---

## 1. With only two users, VRAM buys quality, not throughput

This is the structural difference from sizing a department. Thirty people spend
their memory on KV cache for concurrent sessions. Two people have memory to
spare, so they should spend it on **a better model**.

```bash
ai-bunker recommend --team 2 --model qwen3-coder-next --vision qwen3-vl-8b
```

| Machine | Total | Best coder model | Speed | Sequences | Context |
|---|---:|---|---:|---:|---:|
| **MacBook Pro M2 Max 96 GB** *(already owned)* | **$0** | Qwen3-Coder-Next | 27 tok/s | 5 | 256k |
| **Mac Studio M4 Max 128 GB** | $4,000 | Qwen3-Coder-Next | 36 tok/s | 11 | 256k |
| **Mac Studio M3 Ultra 96 GB** | **$5,600** | Qwen3-Coder-Next | **55 tok/s** | 23 | 256k |
| RTX PRO 5000 Blackwell 72 GB | $12,600 | Qwen3-Coder-Next | 90 tok/s | 16 | 256k |
| RTX PRO 5000 Blackwell 48 GB | $10,200 | *does not fit* | — | — | — |
| RTX PRO 6000 Blackwell 96 GB | $20,000 | Qwen3-Coder-Next | 120 tok/s | 47 | 256k |
| DGX Spark 128 GB | $6,950 | 18 tok/s — below the floor | — | 0 | — |

Two things in that table deserve to be said out loud.

**The 48 GB NVIDIA card cannot run the best model at all.** 45 GiB of weights
plus a vision model plus overhead does not fit in 48 GiB. On NVIDIA, the
entry ticket for Qwen3-Coder-Next is the **72 GB** card at $12,600. On Apple it
is a $5,600 Mac Studio, because unified memory is cheap and GDDR7 — graphics
double data rate memory, seventh generation — is not.

**The DGX Spark still loses, but not for the reason usually given.** It is not
short of memory — it has 128 GB. At 273 GB/s it serves the best coder model at
18 tok/s, just under the floor, and the dense 24B at 6.5 tok/s. It is a
bandwidth problem, and buying more of them does not fix it: bandwidth does not
aggregate across machines for a single stream.

---

## 2. The recommendation

### Step zero, and it is free: measure the machine you have

The arithmetic says a 96 GB M2 Max already serves Qwen3-Coder-Next at ~27 tok/s
with a 256k window — above the comfort floor, for two people, at zero cost.

That is a **projection, not a measurement**, and this project's whole argument
is that the difference matters. Before any purchase:

```bash
ollama pull qwen3-coder-next          # or the GGUF/MLX quant of the day
ai-bunker detect                      # confirm the machine os-helper sees
# then run a real agent session against it and time a real patch
```

If it holds 20+ tok/s under an actual coding session, two consultants have a
working sovereign setup for nothing, and every number below becomes a question
about comfort rather than feasibility. If it does not, you have a measurement
instead of a brochure, and the next step is informed.

Caveats that could sink it, in order of likelihood: macOS caps GPU-usable
unified memory (raise it with `iogpu.wired_limit_mb`); a laptop sleeps, travels,
and is also running the editor; and MoE throughput on Metal is less predictable
than the roofline suggests.

#### One thing here is measured rather than projected

Everything above is arithmetic. This is not. On an **Apple M2 Max, 96 GiB,
400 GB/s nominal**, serving **qwen3-vl:4b (Q4_K_M) through Ollama 0.40.6**,
decoding 128 tokens, median of three per point, three independent runs:

| Prompt tokens | Run 1 | Run 2 | Run 3 |
|---:|---:|---:|---:|
| 216 | 36.0 | 22.3 | 20.8 |
| 3,016 | 36.1 | 22.1 | 27.4 |
| 12,016 | 31.2 | 16.5 | 20.4 |
| 22,016 | 25.3 | 13.9 | 15.1 |
| 32,016 | **16.4** | **11.5** | **12.4** |
| *fall, short to 32k* | *2.20x* | *1.93x* | *1.67x* |

Two things are in that table, and only one of them is a number worth quoting.

**The robust finding: a 32k prompt decodes at roughly half the rate of a short
one.** Every run agrees on the direction and lands between 1.7x and 2.2x; the
fitted slope sits between 0.99 and 1.35 ms per 1,000 context tokens. Context is
not only a memory cost that decides whether a model fits. It is a read that
happens on every decoded token forever, and it is the single largest thing a
harness controls.

That is the measured version of the argument §4 makes from arithmetic, and it
is why this project puts the budget in the server. A session that lets its
context drift to 32k is not using a slightly fuller machine; it is using a
machine that answers at half the speed.

**The fragile finding: the absolute rate moved by 1.6x between runs** — 36 tok/s
and 20.8 tok/s for the same 216-token prompt — while the spread *within* each
run stayed under 1.6 tok/s. A laptop that is also running an editor, a browser
and a build is the normal case, so a single confident number from one is worth
very little. `scripts/bench_context.py` flags wide spreads and non-monotone
points rather than printing a clean-looking table over a busy machine.

What this does **not** establish, said plainly:

- It is a 4B dense vision-language model (VLM), not the 80B MoE coder the
  recommendation rests on.
  The shape of the curve should carry over; the absolute numbers will not.
- It does **not** validate the 70% bandwidth-efficiency assumption. Decode
  time per token is `fixed overhead + bytes / bandwidth`, and one model size
  cannot separate the two terms. Charging the whole intercept to the weight
  read gives 141 GB/s, 35% of nominal — a **lower bound** on efficiency, not a
  measurement of it, because any real fixed overhead has been billed to
  bandwidth. A second model of a different size would settle it, and the 35%
  should not be quoted as though it already had.
- One engine on one platform. llama.cpp on Metal and vLLM on CUDA — NVIDIA's
  Compute Unified Device Architecture — do not carry the same overheads.

One pleasant check does fall out: the slope implies roughly 160 KiB of KV read
per context token at nominal bandwidth, which is within noise of the geometry
`kv_gib()` computes for models of this shape.

Reproduce it with `python scripts/bench_context.py` (see §5).

### If it is not enough: Mac Studio M3 Ultra 96 GB — ~$5,600

- 819 GB/s, **twice** the M2 Max, serving the best open coder at **~55 tok/s**.
- A complete machine. No chassis to spec, no 600 W card, no rack, silent,
  270 W. For a two-person outfit that is not a detail — it is the difference
  between a server and a project to build a server.
- 96 GB of unified memory holds the 80B coder, an 8B vision model and the
  embedder at once, with room left over.
- Skip the M4 Max (546 GB/s) unless budget is binding: $1,600 less for a third
  less bandwidth, which is exactly the axis that matters.

### If you need vision with reliable structured output: RTX PRO 5000 Blackwell 72 GB — ~$12,600

This is the one thing Apple cannot do today, and it is worth stating precisely
because it is the only argument that justifies doubling the spend.

Driving a vision-language model from an agent means **constrained decoding**:
the model must return JavaScript Object Notation (JSON) matching a schema,
every time. vLLM has guided
decoding; Ollama's `format=` equivalent is weaker, and on the Qwen3-VL
reasoning variants it returns an **empty response**, which looks like a timeout
and is not. vLLM has no macOS runtime. So:

> **Vision + schema-constrained output ⇒ vLLM ⇒ Linux + a discrete NVIDIA GPU.**

If that is the requirement, the 72 GB RTX PRO 5000 is the cheapest card that
holds the best coder model: ~$9,600 for the card, ~$12,600 as a node,
1,344 GB/s, 90 tok/s, 300 W — it fits a workstation chassis and a normal wall
socket, which the 600 W RTX PRO 6000 does not.

Same die, same bus and same power as the 48 GB version; the extra $2,400 buys
24 GiB and no bandwidth. For this plan that 24 GiB is the difference between
running the best model and not running it, so it is the right $2,400.

### What to refuse

| Machine | Price | Why |
|---|---:|---|
| DGX Spark | $6,950 | 18 tok/s on the best model, 6.5 on a dense 24B. Capacity without bandwidth. |
| RTX PRO 5000 48 GB | $10,200 | Cannot hold the best model. More expensive than a Mac Studio that can. |
| RTX PRO 6000 96 GB | $20,000 | Correct for thirty people. For two it is ~$10,000 of headroom nobody will reach. |
| H100 80 GB | $40,000 | Fastest per stream and irrelevant at this scale. |
| RTX 5090 32 GB | $7,500 | Fast, and 32 GB holds a dense 24B with almost no KV cache. Consumer card, no ECC — error-correcting code — memory. |

---

## 3. Buying is not obviously right at two people

Say it before the quote is signed.

| Path | Cost | Notes |
|---|---:|---|
| Measure the existing Mac | **$0** | Possibly sufficient. Start here. |
| Mac Studio M3 Ultra 96 GB | $5,600 once | $2,800/person. Pays back against two commercial seats in ~14 months. |
| RTX PRO 5000 72 GB node | $12,600 once | $6,300/person. Only justified by the vision requirement. |
| Rent an equivalent GPU | ~$350/month | 176 GPU-hours a month at $1.64–5.50/hr. Break-even against the Mac Studio: ~16 months; against the NVIDIA node: ~29 months. |
| Premium routes only | ~$400/month | Two commercial seats. No hardware, no operations, no sovereignty. |

The GPU market moved roughly 80% in eighteen months, in the wrong direction for
a buyer. A card bought today is cheap-looking in two years and obsolete in
three. **If sovereignty is a preference, rent or route. If it is a requirement
— client code under an NDA, a non-disclosure agreement; data residency in a
tender — the calculation above is
irrelevant and the answer is the machine.**

---

## 4. The cheapest upgrade is not hardware

The sizing is more sensitive to the **average live context per session** than to
almost anything on the invoice, and that figure belongs to the harness, not to
the card.

| Average live context | Sequences on a Mac Studio M3 Ultra |
|---:|---:|
| 32k — bounded reads, indexed charter, early compaction | **23** |
| 64k — an agent given a window and left to fill it | **11** |

An agent that pastes the whole standards document into every prompt, reads
files whole instead of in slices, and never compacts halves the machine for
identical output. At two people that buys comfort; at scale it buys hardware.
Either way it is the measurable argument for everything else in this repository.

---

## 5. Reproducing this

```bash
ai-bunker recommend --team 2 --model qwen3-coder-next --vision qwen3-vl-8b
ai-bunker recommend --team 2                          # the dense, safe plan
ai-bunker sizing --accelerator mac-studio-m3-ultra-96 --model qwen3-coder-next
ai-bunker compare                                     # every machine, one line
ai-bunker catalog                                     # the facts, with provenance
ai-bunker detect                                      # this machine
```

The one figure here that is measured rather than projected, against any
engine with an Ollama-compatible application programming interface (API):

```bash
ollama serve &
ollama pull qwen3-vl:4b                     # or whatever is already local
python scripts/bench_context.py             # ~4 minutes, prints the table in §2
```

It sweeps the prompt length, fits `ms/token = a + b x context`, and reports the
slope — the part of decode time that context is responsible for. It refuses to
present the intercept as a bandwidth measurement, because with one model size
it is not one, and it flags wide spreads and non-monotone points rather than
printing a tidy table over a machine that was busy. Run it more than once: the
slope repeats, the absolute rate does not.

The assumptions that move the answer most:

```bash
--comfort-tps 30        # a stricter floor: fewer machines qualify
--live-context 65536    # an undisciplined harness: halves every machine
--duty-cycle 0.4        # heavier agentic use
--simultaneity 1.0      # both of you, always, at the same time
```

## 6. Sources

Prices and specifications surveyed 2026-10-19. The GPU market moved roughly 80%
in eighteen months; re-survey before buying.

- [DGX Spark measured tokens/second by model](https://explainx.ai/blog/nvidia-dgx-spark-local-llm-best-setup-2026)
- [DGX Spark repricing and 64 GB configuration](https://www.theregister.com/systems/2026/10/02/nvidia-debuts-4999-dgx-spark-with-half-the-ram-and-storage-amid-memory-crunch/5300622)
- [Mac Studio M3 Ultra / M4 Max bandwidth and LLM throughput](https://insiderllm.com/guides/m4-max-ultra-local-llms-apple-silicon/)
- [RTX PRO 5000 Blackwell 48 GB specifications](https://www.pny.com/nvidia-rtx-pro-5000-blackwell)
- [RTX PRO 5000 Blackwell 72 GB specifications and comparison](https://packet.ai/blog/rtx-pro-5000-blackwell-gpu-cloud)
- [RTX PRO 5000 Blackwell 72 GB street pricing](https://gpuprix.com/us/gpus/rtx-pro-5000-blackwell-72gb)
- [RTX PRO 6000 Blackwell pricing, October 2026](https://www.thundercompute.com/blog/nvidia-rtx-pro-6000-pricing)
- [RTX 5090 street pricing in 2026](https://finance.biggo.com/news/f1c72b65-a71b-48f2-8ff0-0cb775d1a797)
- [Qwen3-Coder-Next model card](https://huggingface.co/Qwen/Qwen3-Coder-Next)
- [Qwen3-Coder-Next local serving guide](https://unsloth.ai/docs/models/qwen3-coder-next)
- [vLLM tool calling and parser selection](https://docs.vllm.ai/en/latest/features/tool_calling/)
