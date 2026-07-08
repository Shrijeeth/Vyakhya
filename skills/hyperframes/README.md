# skills/hyperframes — HyperFrames Agno skill

The HyperFrames **Agno `LocalSkills`** directory. Loaded by the design-time **Block-Author agent**:

```python
from agno.skills import Skills, LocalSkills
block_author = Agent(model=..., skills=Skills(loaders=[LocalSkills("./skills/hyperframes")]))
```

Used to **author new `visual.type` blocks** (HyperFrames component + params schema + editor control) into `@vyakhya/compiler`'s registry — LLM writes HTML **once per block type**, then it's deterministic forever. **Not** on the runtime render path.

> Populate with the HyperFrames `SKILL.md` (+ `scripts/`, `references/`). Fetch via the HyperFrames CLI / skill distribution.
