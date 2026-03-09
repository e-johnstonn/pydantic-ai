from __future__ import annotations as _annotations

from pathlib import Path
from typing import Any, cast

from main import on_page_content, on_post_page
from mkdocs.structure.files import File
from mkdocs.structure.pages import Page

from tests._inline_snapshot import snapshot


def make_page(*, site_dir: Path, src_path: str, title: str) -> tuple[Page, dict[str, Any]]:
    config: dict[str, Any] = {
        'site_url': 'https://ai.pydantic.dev',
        'site_dir': str(site_dir),
        'repo_url': 'https://github.com/pydantic/pydantic-ai',
        'edit_uri': 'edit/main/docs/',
    }
    file = File(src_path, 'docs', str(site_dir), True)
    page = Page(title, file, cast(Any, config))
    return page, config


def test_copy_markdown_uses_rendered_page_content(tmp_path: Path):
    page, config = make_page(site_dir=tmp_path, src_path='index.md', title='Test Page')

    html = """
<p>Intro <a href="tools/">Tools</a>.</p>
<div class="tabbed-set tabbed-alternate">
  <div class="tabbed-labels"><label>First Tab</label><label>Second Tab</label></div>
  <div class="tabbed-content">
    <div class="tabbed-block">
      <div class="language-python highlight"><span class="filename"><a href="gateway/">Learn about Gateway</a> hello_world.py</span><pre><code>print("hi")\n</code></pre></div>
    </div>
    <div class="tabbed-block">
      <p>Second body with an <autoref>autoref</autoref>.</p>
    </div>
  </div>
</div>
<form><input type="email"></form>
<details class="mkdocstrings-source"><summary>Source code in <code>x.py</code></summary><div class="language-python highlight"><pre><code>print("secret")\n</code></pre></div></details>
"""

    returned_html = on_page_content(html, page, cast(Any, config), cast(Any, []))

    assert returned_html == html
    assert page.meta['copy_markdown_path'] == 'index.md'
    assert page.meta['_copy_markdown_content'] == snapshot("""\
# Test Page

Intro [Tools](https://ai.pydantic.dev/tools/index.md).

**First Tab**

[Learn about Gateway](https://ai.pydantic.dev/gateway/index.md) hello_world.py

```python
print("hi")
```

**Second Tab**

Second body with an autoref.
""")


def test_on_post_page_writes_nested_markdown_sidecar(tmp_path: Path):
    page, config = make_page(site_dir=tmp_path, src_path='api/agent.md', title='API Agent')

    html = """
<div class="language-python highlight"><table class="highlighttable"><tbody><tr><td class="linenos"><div class="linenodiv"><pre>1\n2\n</pre></div></td><td class="code"><div><pre><code>from pydantic_ai import Agent\nagent = Agent('openai:gpt-5.2')\n</code></pre></div></td></tr></tbody></table></div>
<p><a href="../models/openai/">OpenAI docs</a></p>
"""

    on_page_content(html, page, cast(Any, config), cast(Any, []))
    returned_output = on_post_page('<html></html>', page, cast(Any, config))

    assert returned_output == '<html></html>'
    assert (tmp_path / 'api' / 'agent' / 'index.md').read_text(encoding='utf-8') == snapshot("""\
# API Agent

```python
from pydantic_ai import Agent
agent = Agent('openai:gpt-5.2')
```

[OpenAI docs](https://ai.pydantic.dev/api/models/openai/index.md)
""")
