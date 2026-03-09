from __future__ import annotations as _annotations

import html as html_lib
import re
import time
import urllib.parse
from itertools import chain
from pathlib import Path

import mdformat
from bs4 import BeautifulSoup as Soup, NavigableString, Tag
from jinja2 import Environment
from markdownify import ATX, MarkdownConverter
from mkdocs.config import Config
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page
from snippets import inject_snippets

DOCS_ROOT = Path(__file__).parent.parent


def _copy_markdown_language(tag: Tag) -> str:
    for css_class in chain(tag.get('class') or (), (tag.parent.get('class') or ()) if tag.parent else ()):
        if css_class.startswith('language-'):
            return css_class[9:]
    return ''


_COPY_MARKDOWN_CONVERTER = MarkdownConverter(
    bullets='-',
    code_language_callback=_copy_markdown_language,
    escape_underscores=False,
    heading_style=ATX,
)


def on_page_markdown(markdown: str, page: Page, config: Config, files: Files) -> str:
    """Called on each file after it is read and before it is converted to HTML."""
    relative_path = DOCS_ROOT / page.file.src_uri
    markdown = inject_snippets(markdown, relative_path.parent)
    markdown = replace_uv_python_run(markdown)
    markdown = render_examples(markdown)
    markdown = render_video(markdown)
    markdown = create_gateway_toggle(markdown, relative_path)
    return markdown


def on_page_content(html: str, page: Page, config: Config, files: Files) -> str:
    markdown_path = _copy_markdown_path(page.file.dest_uri)
    if markdown_path is None:
        return html

    page.meta['_copy_markdown_content'] = _render_copy_markdown(html, page, config)
    page.meta['copy_markdown_path'] = markdown_path
    return html


def on_post_page(output: str, page: Page, config: Config) -> str:
    markdown = page.meta.pop('_copy_markdown_content', None)
    if not isinstance(markdown, str):
        return output

    markdown_path = _copy_markdown_path(page.file.dest_uri)
    if markdown_path is None:
        return output

    markdown_path = Path(config['site_dir']) / markdown_path
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown, encoding='utf-8')
    return output


def _copy_markdown_path(dest_uri: str) -> str | None:
    if not dest_uri.endswith('.html'):
        return None
    return Path(dest_uri).with_suffix('.md').as_posix()


def _render_copy_markdown(html: str, page: Page, config: Config) -> str:
    soup = Soup(html, 'html.parser')
    _prepare_copy_markdown_soup(soup, page)
    _convert_copy_markdown_links_to_absolute(soup, config['site_url'], page.file.dest_uri)
    return mdformat.text(
        _COPY_MARKDOWN_CONVERTER.convert_soup(soup),
        options={'wrap': 'no'},
        extensions=('tables',),
    )


def _prepare_copy_markdown_soup(soup: Soup, page: Page) -> None:
    if soup.find('h1') is None and page.title is not None:
        title = soup.new_tag('h1')
        title.string = str(page.title)
        soup.insert(0, title)

    for tabbed_set in soup.find_all('div', class_='tabbed-set'):
        _flatten_tabbed_set(soup, tabbed_set)

    for filename in soup.find_all('span', class_='filename'):
        filename.name = 'p'
        filename['class'] = ['code-title']

    _autoclean_copy_markdown_soup(soup)


def _flatten_tabbed_set(soup: Soup, tabbed_set: Tag) -> None:
    labels = [label.get_text(' ', strip=True) for label in tabbed_set.select('.tabbed-labels > label')]
    blocks = tabbed_set.select('.tabbed-content > .tabbed-block')

    replacement = soup.new_tag('div')
    if labels and len(labels) == len(blocks):
        for label, block in zip(labels, blocks):
            title = soup.new_tag('p')
            strong = soup.new_tag('strong')
            strong.string = label
            title.append(strong)
            replacement.append(title)
            for child in list(block.contents):
                replacement.append(child.extract())
    else:
        for child in list(tabbed_set.contents):
            replacement.append(child.extract())

    tabbed_set.replace_with(replacement)


def _autoclean_copy_markdown_soup(soup: Soup) -> None:
    for element in soup.find_all(_should_remove_from_copy_markdown):
        element.decompose()

    for element in soup.find_all('autoref'):
        element.replace_with(NavigableString(element.get_text()))

    for element in soup.find_all('div', class_='doc-md-description'):
        element.replace_with(NavigableString(element.get_text().strip()))

    for element in soup.find_all('span', class_='doc-labels'):
        element.decompose()

    for element in soup.find_all('table', class_='highlighttable'):
        code = element.find('code')
        if code is None:
            continue
        element.replace_with(Soup(f'<pre>{html_lib.escape(code.get_text())}</pre>', 'html.parser'))


def _should_remove_from_copy_markdown(tag: Tag) -> bool:
    if tag.name in {'form', 'img', 'svg'}:
        return True

    if tag.name == 'a' and tag.find(['img', 'svg']) is not None:
        return True

    classes = tag.get('class') or ()
    if tag.name == 'a' and 'headerlink' in classes:
        return True
    if 'twemoji' in classes:
        return True
    if 'tabbed-labels' in classes:
        return True
    if tag.name == 'details' and 'mkdocstrings-source' in classes:
        return True

    return False


def _convert_copy_markdown_links_to_absolute(soup: Soup, base_uri: str, page_uri: str) -> None:
    current_dir = Path(page_uri).parent.as_posix()

    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if not isinstance(href, str) or not href:
            continue
        link['href'] = _convert_copy_markdown_link_to_absolute(href, base_uri, current_dir)


def _convert_copy_markdown_link_to_absolute(href: str, base_uri: str, current_dir: str) -> str:
    if href.startswith('/') or href.startswith('#'):
        return href

    try:
        if urllib.parse.urlsplit(href).scheme:
            return href
    except ValueError:
        return href

    relative_base = urllib.parse.urljoin(base_uri, current_dir + '/') if current_dir else base_uri
    final_href = urllib.parse.urljoin(relative_base, href)
    parsed_href = urllib.parse.urlsplit(final_href)
    path = parsed_href.path
    if path.endswith('/'):
        path += 'index.md'
    elif not Path(path).suffix:
        path += '/index.md'
    return urllib.parse.urlunsplit(parsed_href._replace(path=path))


# path to the main mkdocs material bundle file, found during `on_env`
bundle_path: Path | None = None


def on_env(env: Environment, config: Config, files: Files) -> Environment:
    global bundle_path
    for file in files:
        if re.match('assets/javascripts/bundle.[a-z0-9]+.min.js', file.src_uri):
            bundle_path = Path(file.dest_dir) / file.src_uri

    env.globals['build_timestamp'] = str(int(time.time()))
    return env


def on_post_build(config: Config) -> None:
    """Inject extra CSS into mermaid styles to avoid titles being the same color as the background in dark mode."""
    assert bundle_path is not None
    if bundle_path.exists():
        content = bundle_path.read_text(encoding='utf-8')
        content, _ = re.subn(r'}(\.statediagram)', '}.statediagramTitleText{fill:#888}\1', content, count=1)
        bundle_path.write_text(content, encoding='utf-8')


def replace_uv_python_run(markdown: str) -> str:
    return re.sub(r'```bash\n(.*?)(python/uv[\- ]run|pip/uv[\- ]add|py-cli)(.+?)\n```', sub_run, markdown)


def sub_run(m: re.Match[str]) -> str:
    prefix = m.group(1)
    command = m.group(2)
    if 'pip' in command:
        pip_base = 'pip install'
        uv_base = 'uv add'
    elif command == 'py-cli':
        pip_base = ''
        uv_base = 'uv run'
    else:
        pip_base = 'python'
        uv_base = 'uv run'
    suffix = m.group(3)
    return f"""\
=== "pip"

    ```bash
    {prefix}{pip_base}{suffix}
    ```

=== "uv"

    ```bash
    {prefix}{uv_base}{suffix}
    ```"""


EXAMPLES_DIR = Path(__file__).parent.parent.parent / 'examples'


def render_examples(markdown: str) -> str:
    return re.sub(r'^#! *examples/(.+)', sub_example, markdown, flags=re.M)


def sub_example(m: re.Match[str]) -> str:
    example_path = EXAMPLES_DIR / m.group(1)
    content = example_path.read_text(encoding='utf-8').strip()
    # remove leading docstring which duplicates what's in the docs page
    content = re.sub(r'^""".*?"""', '', content, count=1, flags=re.S).strip()

    return content


def render_video(markdown: str) -> str:
    return re.sub(r'\{\{ *video\((["\'])(.+?)\1(?:, (\d+))?(?:, (\d+))?\) *\}\}', sub_cf_video, markdown)


def sub_cf_video(m: re.Match[str]) -> str:
    video_id = m.group(2)
    time = m.group(3)
    time = f'{time}s' if time else ''
    padding_top = m.group(4) or '67'

    domain = 'https://customer-nmegqx24430okhaq.cloudflarestream.com'
    poster = f'{domain}/{video_id}/thumbnails/thumbnail.jpg?time={time}&height=600'
    return f"""
<div style="position: relative; padding-top: {padding_top}%;">
  <iframe
    src="{domain}/{video_id}/iframe?poster={urllib.parse.quote_plus(poster)}"
    loading="lazy"
    style="border: none; position: absolute; top: 0; left: 0; height: 100%; width: 100%;"
    allow="accelerometer; gyroscope; autoplay; encrypted-media; picture-in-picture;"
    allowfullscreen="true"
  ></iframe>
</div>
"""


def create_gateway_toggle(markdown: str, relative_path: Path) -> str:
    """Transform Python code blocks with Agent() calls to show both Pydantic AI and Gateway versions."""
    # Pattern matches Python code blocks with or without attributes, and optional annotation definitions after
    # Annotation definitions are numbered list items like "1. Some text" that follow the code block
    return re.sub(
        r'```py(?:thon)?(?: *\{?([^}\n]*)\}?)?\n(.*?)\n```(\n\n(?:\d+\..+?\n)+?\n)?',
        lambda m: transform_gateway_code_block(m, relative_path),
        markdown,
        flags=re.MULTILINE | re.DOTALL,
    )


# Mapping of provider names to their canonical gateway form
GATEWAY_MODEL_MAP = {
    'anthropic': 'anthropic',
    'openai': 'openai',
    'openai-responses': 'openai-responses',
    'openai-chat': 'openai',
    'bedrock': 'bedrock',
    'google-gla': 'gemini',
    'google-vertex': 'google-vertex',
    'groq': 'groq',
}
# Models that should get gateway transformation
GATEWAY_MODELS = tuple(GATEWAY_MODEL_MAP.keys())


def transform_gateway_code_block(m: re.Match[str], relative_path: Path) -> str:
    """Transform a single code block to show both versions if it contains Agent() calls."""
    attrs = m.group(1) or ''
    code = m.group(2)
    annotations = m.group(3) or ''  # Capture annotation definitions if present

    # Simple check: does the code contain both "Agent(" and a quoted string?
    if 'Agent(' not in code:
        attrs_str = f' {{{attrs}}}' if attrs else ''
        return f'```python{attrs_str}\n{code}\n```{annotations}'

    # Check if code contains Agent() with a model that should be transformed
    # Look for Agent(...'model:...' or Agent(..."model:..."
    agent_pattern = r'Agent\((?:(?!["\']).)*([\"\'])([^"\']+)\1'
    agent_match = re.search(agent_pattern, code, flags=re.DOTALL)

    if not agent_match:
        # No Agent() with string literal found
        attrs_str = f' {{{attrs}}}' if attrs else ''
        return f'```python{attrs_str}\n{code}\n```{annotations}'

    model_string = agent_match.group(2)
    # Check if model starts with one of the gateway-supported models
    should_transform = any(model_string.startswith(f'{model}:') for model in GATEWAY_MODELS)

    if not should_transform:
        # Model doesn't match gateway models, return original
        attrs_str = f' {{{attrs}}}' if attrs else ''
        return f'```python{attrs_str}\n{code}\n```{annotations}'

    # Transform the code for gateway version
    def replace_agent_model(match: re.Match[str]) -> str:
        """Replace model string with gateway/ prefix if it's a supported provider."""
        full_match = match.group(0)
        quote = match.group(1)
        model = match.group(2)

        for provider, gateway_provider in GATEWAY_MODEL_MAP.items():
            if model.startswith(f'{provider}:'):
                new_model = model.replace(f'{provider}:', f'gateway/{gateway_provider}:', 1)
                return full_match.replace(f'{quote}{model}{quote}', f'{quote}{new_model}{quote}', 1)

        return full_match

    # This pattern finds: "Agent(" followed by anything (lazy), then the first quoted string
    gateway_code = re.sub(
        agent_pattern,
        replace_agent_model,
        code,
        flags=re.DOTALL,
    )

    # Build attributes string
    docs_path = DOCS_ROOT / 'gateway'

    relative_path_to_gateway = docs_path.relative_to(relative_path, walk_up=True)
    link = f"<a href='{relative_path_to_gateway}' style='float: right;'>Learn about Gateway</a>"
    attrs_str = f' {{{attrs}}}' if attrs else ''

    if 'title="' in attrs:
        gateway_attrs = attrs.replace('title="', f'title="{link} ', 1)
    else:
        gateway_attrs = attrs + f' title="{link}"'
    gateway_attrs_str = f' {{{gateway_attrs}}}'

    # Indent code lines for proper markdown formatting within tabs
    # Always add 4 spaces to every line (even empty ones) to preserve annotations
    code_lines = code.split('\n')
    indented_code = '\n'.join('    ' + line for line in code_lines)

    gateway_code_lines = gateway_code.split('\n')
    indented_gateway_code = '\n'.join('    ' + line for line in gateway_code_lines)

    # Indent annotation definitions if present (need to be inside tabs for Material to work)
    indented_annotations = ''
    if annotations:
        # Remove surrounding newlines and indent each line with 4 spaces
        annotation_lines = annotations.strip().split('\n')
        indented_annotations = '\n\n' + '\n'.join('    ' + line for line in annotation_lines) + '\n\n'

    return f"""\
=== "With Pydantic AI Gateway"

    ```python{gateway_attrs_str}
{indented_gateway_code}
    ```{indented_annotations}

=== "Directly to Provider API"

    ```python{attrs_str}
{indented_code}
    ```{indented_annotations}"""
