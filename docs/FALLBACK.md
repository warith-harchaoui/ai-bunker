# When the model does not fit

Layer-by-layer streaming, what it makes possible, and what it costs — measured
on this repository's own hardware on **2026-10-27**, with the command that
reproduces every number.

> The rest of this project sizes a machine that **holds** a model. This
> document answers the other question: what happens when it does not, and the
> choice is between a smaller model and a slower one.
>
> Every figure comes from `ai-bunker fallback`. One of them is a measurement of
> a real drive; the rest is arithmetic over that measurement, and the two are
> labelled apart throughout.

**The notation, once.** A **GPU** is a graphics processing unit, the chip a
model's weights are read from, and **VRAM** is its video random-access memory.
**RAM** is the machine's ordinary random-access memory. An **LLM** is a large
language model, and **B** counts billions of parameters, so a *24B* model
carries 24 billion weights. **bf16**, **FP8** and **AWQ4** say how many bits
each weight is stored on: bf16 is the 16-bit *brain floating point* format
models are trained in, FP8 is 8-bit floating point, and AWQ4 is
*activation-aware weight quantization* at 4 bits. **GB** is gigabytes and
**GiB** gibibytes, the powers-of-two kind, 2³⁰ bytes — about 7% more, which is
why a 24B model at 8 bits a weight reads as 25 GiB. **tok/s** is tokens per
second. The **KV cache** is the key–value cache, what a model keeps about the
tokens already in a conversation. A **MoE** is a *mixture of experts*, a model
that routes each token through a fraction of its weights. An **SSD** is a
solid-state drive, and **NVMe** — *Non-Volatile Memory express* — is the
interface the fast ones use, over **PCIe**, the *Peripheral Component
Interconnect express* bus. The slower buses a drive can hang off are **SATA**,
*Serial Advanced Technology Attachment*, and **USB**, the *Universal Serial Bus*.

**The short answer.** Streaming makes a model that does not fit **runnable**,
and it does not make it **servable**. On every machine in this project's
catalogue it lands between 0.1 and 0.5 tok/s, which is one to three hundred
times below the floor at which a coding agent stays usable. That is not a
disappointment to be engineered away; it is the arithmetic, and the useful move
is to know which side of it you are on before spending an afternoon finding
out. Use it for work nobody is watching. Never put it behind an interactive
agent.

---

## 0. The one fact that decides everything

This project's whole speed model is one line. Generating a token requires
reading the weights out of the device that holds them, once:

```
tokens/second  ≤  bandwidth  /  bytes read per token
```

Resident serving reads them out of memory. Layer streaming reads them off
**storage**. Same arithmetic, different device — and on this machine the two
devices are not close:

| Device | Read bandwidth | How we know |
|---|---:|---|
| Unified memory, Apple M2 Max | 400 GB/s | vendor |
| Internal NVMe SSD, same machine | **5.6 GB/s** | **measured, see §5** |

**Seventy-one times.** That ratio is the entire content of this document. Every
other number below follows from it, and nothing in the engine's design — not
prefetching, not compression, not a faster card — changes it by more than a
small factor.

### Three consequences, and all three are load-bearing

**The read is the whole checkpoint, not the active part.** A layer is loaded
whole, so every expert of every layer crosses the bus whether the router picks
it or not. The mixture-of-experts economics that make an 80B/3B model the
fastest thing in `catalog/serving.yaml` are a property of *resident* serving
and they do not survive the move to storage. §2 is that inversion, in numbers.

**Prefill is nearly free and generated length is ruinous.** A prompt of any
length makes one pass over the layers, because the whole prompt goes through
each layer while it is resident. So a 32,000-token prompt costs about one
token's worth of reads — and then every single generated token costs another
full pass. This is the exact opposite of the cost shape everywhere else in this
project, where [`docs/SIZING.md`](SIZING.md) spends four sections on why
context is the most expensive thing a harness controls. Under streaming,
context is almost free and the answer is the whole bill.

**The page cache helps precisely where it should not be used.** Shards the
operating system keeps in free memory are re-read at memory speed rather than
off the drive. But a machine with enough free memory to cache the checkpoint is
a machine that could have *held* the checkpoint, where a memory-mapped resident
engine is strictly faster. So the regime streaming exists for is the regime
where the cache cannot save it, and `ai-bunker fallback` says so out loud
rather than reporting a half-cached figure as a storage one.

---

## 1. What streaming actually buys

One thing, and it is real: **the capacity wall disappears.**

```bash
ai-bunker fallback --model qwen3-coder-next --accelerator rtx-4090 --disk 5.6
```

| Model | Checkpoint | Device needed | Context | Speed | A 500-token answer |
|---|---:|---:|---:|---:|---:|
| Devstral Small 2 24B, FP8 | 25 GiB | **4.0 GiB** | 8,192 | 0.22 tok/s | 38 min |
| Qwen3-Coder-Next 80B, AWQ4 | 45 GiB | **3.8 GiB** | 8,192 | 0.11 tok/s | 1.3 h |

An 80-billion-parameter model, running inside **four gibibytes** of device
memory. That is the claim AirLLM makes and it holds: two resident layer shards
and a KV cache are all that stay on the device, and a shard of a 48-layer
checkpoint is under a gibibyte.

**What binds instead is the KV cache**, which streaming does not move. The
weights go to storage; the cache stays on the device, and on a small card it is
what decides the context. The 262,144 tokens the catalogue lists for Devstral
need 20 GiB of bf16 cache, so `ai-bunker fallback` halves the context until it
fits beside the shards and says that it did. Streaming removes the wall for the
checkpoint. It does not remove it for a single layer, and a device too small
for one shard is refused with that sentence.

---

## 2. The recommendation inverts, and this is the part to read twice

`docs/SIZING.md` §0 makes an argument this project is quite pleased with: the
best open coding model is *also* the fastest to serve, because 3 billion active
parameters out of 80 billion total means an 80B-class model with 24B-class
latency. Choosing a smaller model to go faster is, there, exactly backwards.

Under streaming it is exactly forwards. One 24 GiB card, nothing cacheable, the
measured 5.6 GB/s drive:

| Model | Checkpoint | Active per token | Streaming | Resident | Ratio |
|---|---:|---:|---:|---:|---:|
| Devstral Small 2 24B, dense | 25 GiB | 25 GiB | **0.177 tok/s** | 26.3 tok/s | 148x |
| Qwen3-Coder-Next 80B MoE | 45 GiB | ~9 GiB | **0.099 tok/s** | 73.0 tok/s | 741x |

The dense 24B is **1.8 times faster** streamed, and the mixture of experts is
the one that loses most by the change — 741 times slower than it would be if it
fitted, against 148. The `active_fraction` column that wins the resident
argument is worth nothing here, because a streaming engine does not hold the
checkpoint and so cannot read a part of it.

Said as a rule: **choose by total checkpoint size, not by active parameters,
the moment the weights come off a disk.** It is the single easiest thing to get
backwards after reading the rest of this repository, which is why
`tests/test_fallback.py` asserts both directions.

---

## 3. The drive is the machine

This is the other structural surprise. Across five very different machines the
answer barely moves, and where it moves it is the drive moving, not the card:

```bash
ai-bunker fallback --model devstral-small-2-24b --accelerator rtx-5090
```

| Machine | Card | Memory bandwidth | Streamed | A 500-token answer |
|---|---:|---:|---:|---:|
| MacBook Pro M2 Max 96 GB | — | 400 GB/s | 0.41 tok/s | 20 min |
| RTX 4090 24 GB | $2,500 | 1,008 GB/s | 0.31 tok/s | 27 min |
| RTX 5090 32 GB | $5,000 | 1,792 GB/s | **0.31 tok/s** | 27 min |
| RTX PRO 5000 48 GB | $7,200 | 1,344 GB/s | 0.32 tok/s | 26 min |
| DGX Spark 128 GB | $6,950 | 273 GB/s | 0.32 tok/s | 26 min |

The 4090 and the 5090 are identical to three decimal places. They have the same
assumed drive, and under streaming that is the only number that matters: a
memory bus of 1,792 GB/s spends its life waiting on 7 GB/s of storage. **Paying
$2,500 more for a card buys nothing at all in this regime.** The money, if
there is money, goes on the drive:

```bash
ai-bunker fallback --model devstral-small-2-24b --storage nvme-gen5
```

| Storage class | Read | Speed | A 500-token answer | Verdict |
|---|---:|---:|---:|---|
| PCIe 5.0 NVMe | 14.0 GB/s | 0.443 tok/s | 19 min | batch |
| PCIe 4.0 NVMe | 7.0 GB/s | 0.222 tok/s | 38 min | batch |
| Apple internal, **measured** | 5.6 GB/s | 0.177 tok/s | 47 min | batch |
| Network file system, 10 gigabit | 1.1 GB/s | 0.035 tok/s | 4.0 h | overnight |
| External SSD over 10-gigabit USB | 0.9 GB/s | 0.028 tok/s | 4.9 h | overnight |
| SATA SSD | 0.55 GB/s | 0.017 tok/s | 8.0 h | overnight |
| Rotating hard disk | 0.2 GB/s | 0.006 tok/s | 21.9 h | impractical |

A 74-fold spread, from one component. Two practical notes fall out of it. An
external enclosure is ten times worse than the internal drive the checkpoint
was moved off, which is the opposite of what "I'll put the models on the big
external disk" assumes. And streaming layers over a network puts every weight
of every token on a wire, which for this project is a sovereignty question
before it is a speed one.

And the ceiling is worth stating plainly: the fastest storage a consumer slot
offers in 2026 is about 2% of the memory bandwidth of the cards in this
catalogue. **Buying the best drive on the market does not make layer streaming
interactive.** It moves it from forty minutes to twenty.

---

## 4. Compression is the only knob with real leverage

Throughput is bytes divided by bandwidth, so halving the bytes doubles the
speed. AirLLM's block-wise compression quantizes the shards on disk, and that
is the whole mechanism — there is nothing else here that gives a factor of two.

```bash
ai-bunker fallback --model devstral-small-2-24b --disk 5.6 --compression 4bit
```

| What the engine is handed | Bytes read | Speed | A 500-token answer |
|---|---:|---:|---:|
| The FP8 checkpoint as the catalogue lists it | 25.0 GiB | 0.177 tok/s | 47 min |
| bf16 compressed to 8 bits | 25.2 GiB | 0.176 tok/s | 47 min |
| bf16 compressed to 4 bits | **12.6 GiB** | **0.352 tok/s** | **24 min** |

Two things in that table deserve saying out loud.

**8-bit compression buys nothing here, and the reason is not a defect.** It is
measured against a checkpoint that was already 8-bit, and 25.2 GiB against
25.0 is the per-block scales and zero points — which are stored beside the
quantized weights and read with them. Compression helps relative to *what you
would otherwise hand the engine*, and a project that already serves FP8 has
spent that factor.

**4-bit doubles it, and 0.35 tok/s is still not a usable engine.** A factor of
two on a number three orders of magnitude below the floor is a factor of two.
`ai-bunker fallback` refuses `--compression` on a model the catalogue carries
only as an already-quantized community checkpoint, because there is nothing
left to compress and reporting the quarter anyway would promise a throughput
nothing can deliver.

---

## 5. The one measured number

Everything above is arithmetic over a single measurement, so here is the
measurement, and here is what it is not.

On an **Apple M2 Max, 96 GiB**, macOS 26.5.2, by
`python scripts/bench_disk.py`:

| Scratch file | Reads | Uncached | Cached |
|---:|---:|---:|---:|
| 2 GiB, writes *through* the cache | 3 | 13.73 / 13.11 / 12.35 GB/s | — |
| 2 GiB, **writes bypassing the cache** | 3 | **5.61 / 5.49 / 5.65 GB/s** | 13.80 / 13.24 / 14.12 GB/s |
| 8 GiB, writes bypassing the cache | 3 | **5.25 / 5.56 / 5.55 GB/s** | 12.80 / 13.06 / 12.91 GB/s |
| 2 GiB again, an hour later | 3 | **5.65 / 5.67 / 5.68 GB/s** | 12.65 / 11.27 / 12.08 GB/s |

The first row is the mistake, kept because it is the one anybody writing this
benchmark makes. `F_NOCACHE` on the *reading* descriptor stops new pages being
cached; it does not evict the pages the write just put there, and a 2 GiB file
on a 96 GiB machine stays resident. So the first measurement was the page cache
wearing a storage label, at **13.1 GB/s — above what the drive can physically
do**, which is the only reason it was caught. `scripts/bench_disk.py` now sets
`F_NOCACHE` on the writing descriptor too.

Once the write bypasses the cache, the nine remaining readings run from 5.25 to
5.68 GB/s — **8% end to end, under 6% within any one run** — with a median of
**5.6 GB/s**, which is what the catalogue records and what this document uses.
Unlike the throughput sweep in `docs/SIZING.md` §2, where the absolute rate
moved by 1.6x between runs on this same laptop, this figure is stable: a drive
does not care that an editor and a browser are open.

What this does **not** establish, said plainly:

- **One drive, one machine, one filesystem.** The figure is this laptop's. The
  catalogue's other storage classes are vendor peak numbers, labelled as such,
  and `ai-bunker fallback` says so in a warning every time it uses one.
- **It is not a measurement of the engine.** It measures what the device can
  deliver to a sequential reader. Whether AirLLM's prefetch extracts 85% of
  that — the `--disk-efficiency` assumption — is not tested here. The default
  is deliberately generous: being generous and still landing three orders of
  magnitude below the interactive floor is a stronger statement than being
  careful.
- **The cached rate is a syscall-bound copy, not memory bandwidth.** 13 GB/s
  against the machine's 400 is what `read(2)` out of the page cache costs, and
  it is the right figure for the partly-cached term precisely because that is
  how a cached shard is actually fetched.
- **No answer was generated.** Nothing in this document is a measurement of a
  model streamed off a disk. It is a bandwidth measurement and a roofline over
  it, which is the same standing as every projection in `docs/SIZING.md`, and
  it is labelled the same way.

```bash
python scripts/bench_disk.py                     # ~20 s, 2 GiB of scratch
python scripts/bench_disk.py --size-gib 8        # longer, steadier
python scripts/bench_disk.py --path /Volumes/ext # measure another device
```

---

## 6. Activating it: automatic, by hand, or not at all

Three modes, and the default is the conservative one.

```bash
ai-bunker fallback --model qwen3-coder-next --mode off      # report only
ai-bunker fallback --model qwen3-coder-next --mode auto     # decide from this machine
ai-bunker fallback --model qwen3-coder-next --mode on       # because I said so
```

| Mode | Model fits | Model does not fit |
|---|---|---|
| `off` | serve it resident | refuse, and print what streaming would have cost |
| `auto` | serve it resident | stream **if** the verdict clears `--floor`, else refuse |
| `on` | stream, with an objection on the record | stream, with the cost on the record |

`auto` is the "decide from the running machine" position and it is what makes
the fallback safe to leave configured: on a machine where the model fits it
does not engage, and where streaming would be useless it refuses rather than
engaging uselessly. The floor is a verdict name — `interactive`, `batch`,
`overnight`, `impractical` — and `batch` by default, meaning "an answer within
the hour or do not bother".

`on` is the human decision, and it still argues. Asked to stream a model that
fits, it streams and records that this reads the whole checkpoint off a disk
for every token instead of out of memory, at a stated multiple. Asked to stream
something `impractical`, it does so and says it is doing it because it was
asked, not because it is a good idea.

### What `auto` deliberately does not do

**It does not switch engines underneath a running gateway.** A coding agent
pointed at an engine answering at a fifth of a token per second does not
degrade — it hangs, the client times out, and the operator spends the evening
debugging a network problem that is not one. So the automatic part of automatic
is the **decision**, computed from the machine in front of you and printed with
the command it implies. A human starts the engine.

That is the same rule this project already applies to a premium route: the
expensive, surprising path is one somebody writes down. An activated fallback
therefore always carries the sentence that it is not an interactive engine,
whatever the verdict.

### Using it as a gate

`ai-bunker fallback` exits non-zero when the decision is "this machine cannot
usefully run this model", so it works in a script and not only on a terminal:

```bash
if ai-bunker fallback --model qwen3-coder-next --mode auto --floor batch; then
  eval "$(ai-bunker fallback --model qwen3-coder-next --json | jq -r .command)"
fi
```

---

## 7. Running it

The engine is a **separate process** behind an OpenAI-compatible socket, and
the gateway is told about it the way it is told about anything else.

```bash
pip install 'ai-bunker[airllm]'

ai-bunker airllm serve \
  --model /models/Devstral-Small-2-24B \
  --port 8003 \
  --context 8192 \
  --compression 4bit \
  --shards ~/.cache/ai-bunker/shards
```

```yaml
# config/gateway.yaml
upstreams:
  fallback:
    base_url: http://127.0.0.1:8003/v1
    served_context: 8192
    remote: false
    model: /models/Devstral-Small-2-24B

needs:
  # By need, never by default: the interactive needs stay on something resident.
  offline: fallback
```

**There is no fallback-specific configuration key, and that is the design.**
The engine speaks the dialect the gateway already proxies, so screening, the
context budget, the circuit breaker and the decision log apply to a
streamed-off-disk answer exactly as they do to a vLLM one. Nothing in
`gateway.py` changed to make this work.

Four things worth knowing before the first run.

**The first load splits the checkpoint onto disk**, which reads the whole thing,
writes the whole thing again, takes about as long as the download did, and wants
about as much room. `--shards` decides where. Pass `--eager` to pay that cost at
start-up, so a scripted deployment fails when it is launched rather than on the
first request an hour later; without it, `/health` answers `loading` throughout,
which is how an operator tells "working" from "wedged".

**Streaming matters here for the opposite of the usual reason.** A resident
engine streams so the reader sees progress. This one streams so the
*connection survives*: a client waiting forty minutes for a complete body will
give up, and several intermediaries will give up for it. The socket writes a
keepalive comment every five seconds while a layer read is in flight.

**A repository id is refused rather than downloaded.** Handing a loader
`owner/name` makes it fetch from a third-party hub, and this project does not do
that on a default — a local path loads and also sets `HF_HUB_OFFLINE`, so the
loader cannot check a hub for a newer revision either. Downloading is a decision
taken in as many words, with `--allow-download`.

**`bitsandbytes` is not installed by the extra.** Block-wise compression needs
it, it does not build everywhere, and discovering that as a build failure
halfway through `pip install ai-bunker[airllm]` is worse than installing it
knowingly.

---

## 8. Imported, not vendored

This is a design decision with a cost either way, so here is the reasoning.

The part of AirLLM that looks worth copying — "load one layer, run it, free
it" — is twenty lines and is not the work. The work is the per-architecture
layer-name mapping across a dozen model families, the safetensors splitting,
the block-wise quantization of the shards, and the prefetch that keeps the
pipeline fed. That is the half that churns, every time a family ships with its
layers named something new, and a vendored copy of it decays in silence: it
keeps working for the models it knew and refuses the one you actually wanted,
with a `KeyError`.

So `ai_bunker/airllm.py` copies none of it. It renders messages through the
checkpoint's own chat template and frames the result as OpenAI-compatible
JSON — the JavaScript Object Notation shape every client already speaks. Every
decision about *layers* belongs upstream.

It does not even load the checkpoint itself if it can avoid it.
[`best-engine-ai-helper`](https://github.com/warith-harchaoui/best-engine-ai-helper)
is this suite's owner of "which local model, on what hardware, through which
backend", and its `offload` module is the suite's AirLLM adapter — so
`ai_bunker.airllm` prefers `best_engine_ai_helper.airllm_load` and imports
`airllm` directly only when the installed helper does not offer it. The point
is that exactly one place in the suite passes keyword arguments to
`AutoModel.from_pretrained`: a renamed option upstream, a new sharding flag or
a workaround for one model family is then absorbed once rather than in every
package that wanted a streamed model. The direct path is not a preference, it
is the version skew a two-repository suite actually has.

What stays here is what is genuinely missing elsewhere.

**The socket.** The helper's `generate` is a Python call that blocks and
returns a string, because AirLLM is a library and not a daemon. This gateway
proxies the HyperText Transfer Protocol (HTTP) and nothing else, so the
OpenAI-compatible surface — streaming
frames, keepalives, the refusals — is what turns a library into something
`ai_bunker.gateway` can treat as an upstream.

**The server arithmetic.** `ai_bunker/fallback.py` sizes streaming against
`catalog/serving.yaml`: weight footprint per quantization, KV-cache geometry,
the context that cache will actually allow beside the shards, and the
comparison against a priced accelerator. The helper's catalogue does not carry
those — by the same division that makes `ai_bunker/sizing.py` exist alongside
the helper's own `recommend`, and that the catalogue's header has stated since
before any of this.

Three further reasons the shape is this one:

- **Weight.** AirLLM brings PyTorch, transformers and accelerate — around
  2.5 GiB of wheels — and `pip install ai-bunker` must not. It lives behind an
  extra, is imported lazily, and a deployment that only runs `sizing` and
  `doctor` never meets it. The *arithmetic* in this document needs none of it.
- **Licensing.** AirLLM is Apache-2.0 and this project is BSD-3-Clause:
  compatible to depend on, and vendoring would move an Apache notice obligation
  into a Berkeley Software Distribution licensed tree for nothing in return.
- **Process boundary.** The gateway is a proxy, and every upstream it has ever
  talked to is a uniform resource locator, a URL — which is what lets it
  screen, budget and refuse without
  knowing what is at the other end. Importing an inference engine into it would
  put model weights and a generation loop holding the global interpreter lock
  inside the one process whose job is to answer `/health` promptly. This project
  has already fixed that defect once, in the inbound pipeline, and should not
  reintroduce it by a different door.

What *is* owned here is the decision for a **server**: the roofline over this
project's own serving catalogue, the named storage classes, the page-cache
mixing, the context the KV cache will actually allow, the three activation
modes, and the upstream stanza that puts the result behind the gateway. That is
the half AirLLM has no opinion about and the half this repository is for.

---

## 9. Honest limitations

- **No answer has been generated through this path.** The arithmetic is tested
  and the socket is tested against a stub; "AirLLM produces the tokens
  transformers would" is not a claim made anywhere in this repository. The
  stub exists because a real run needs a multi-gibibyte checkpoint and an hour
  of wall clock to produce one paragraph.
- **`--disk-efficiency 0.85` is an assumption, not a measurement.** It is the
  fraction of sequential bandwidth a real shard read achieves, and separating
  it from fixed per-layer overhead needs two checkpoints of different sizes
  streamed on one machine. That experiment has not been run.
- **Layer counts are published for three of the six catalogue models.** For
  the rest a shard is sized at a 48th of the checkpoint and the result says
  `layers_assumed`. Throughput does not depend on the count — only the memory
  requirement does — so the figure that would be wrong is the one deciding
  whether a small card clears the bar at all.
- **One sequence at a time.** There is no batching here, paged or otherwise, so
  a second concurrent request queues behind the first. At these speeds that is
  not the binding problem, but it rules the engine out for anything shared.
- **The KV cache is bf16.** The resident path assumes an 8-bit cache, which is
  a vLLM feature; this path is PyTorch and does not have it. So the context a
  given card allows is roughly half what `docs/SIZING.md` would suggest.
- **macOS support in AirLLM is narrower than its model list.** Upstream
  documents the Apple path as Llama-style architectures only. The arithmetic
  here is indifferent to that; the engine is not.

---

## 10. Reproducing this

```bash
python scripts/bench_disk.py                        # the one measured number
ai-bunker fallback --model qwen3-coder-next --disk 5.6
ai-bunker fallback --model devstral-small-2-24b --accelerator rtx-4090 --disk 5.6
ai-bunker fallback --model devstral-small-2-24b --storage hdd
ai-bunker fallback --model devstral-small-2-24b --compression 4bit --json
ai-bunker catalog                                   # the facts, with provenance
```

The assumptions that move the answer most:

```bash
--disk 14.0              # a PCIe 5.0 drive: everything roughly doubles
--compression 4bit       # halve the bytes, double the speed
--disk-efficiency 0.6    # a less generous view of the prefetch
--answer-tokens 2000     # judge it on a real patch rather than a paragraph
--floor overnight        # accept more before refusing to activate
```

## 11. Sources

- [AirLLM](https://github.com/lyogavin/airllm) — the engine, Apache-2.0
- [AirLLM on the Python Package Index](https://pypi.org/project/airllm/) — version 4.0.0 at
  the time of writing, which pulls `torch>=2.4`, `transformers>=4.49` and
  `accelerate>=1.0`. The `airllm` extra here declares `>=2.11,<5`, matching
  `best-engine-ai-helper[airllm]` exactly, because this package loads
  checkpoints through that one
- [`docs/SIZING.md`](SIZING.md) — the resident sizing this inverts
- [Qwen3-Coder-Next model card](https://huggingface.co/Qwen/Qwen3-Coder-Next)
- `scripts/bench_disk.py` — the measurement, in this repository
- `ai_bunker/fallback.py` — the arithmetic, with every assumption named
- `tests/test_fallback.py` — the claims above, asserted
