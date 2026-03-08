const COPY_MARKDOWN_LABELS = {
  idle: 'Copy page',
  pending: 'Copying...',
  success: 'Copied!',
  error: 'Copy failed',
}

const COPY_BUTTON_SELECTOR = '[data-pydantic-copy-markdown]'

function markdownPathFromLocation(pathname) {
  if (pathname.endsWith('/')) {
    return `${pathname}index.md`
  }

  if (pathname.endsWith('.html')) {
    return pathname.replace(/\.html$/, '.md')
  }

  return `${pathname}/index.md`
}

function markdownUrlForCurrentPage() {
  const path = markdownPathFromLocation(window.location.pathname)
  return new URL(path, window.location.origin)
}

function setCopyButtonState(button, state) {
  const label = COPY_MARKDOWN_LABELS[state]
  button.setAttribute('aria-label', label)
  button.setAttribute('title', label)
  const labelNode = button.querySelector('.pydantic-copy-markdown-label')
  if (labelNode) {
    labelNode.textContent = label
  }
}

async function writeToClipboard(text) {
  if (!navigator.clipboard || !window.isSecureContext) {
    throw new Error('Clipboard API is unavailable')
  }

  await navigator.clipboard.writeText(text)
}

async function copyPageMarkdown(button) {
  button.disabled = true
  setCopyButtonState(button, 'pending')

  try {
    const response = await fetch(markdownUrlForCurrentPage())
    if (!response.ok) {
      throw new Error(`Failed to fetch markdown: ${response.status}`)
    }

    const markdown = await response.text()
    await writeToClipboard(markdown)
    setCopyButtonState(button, 'success')
  } catch (error) {
    console.error(error)
    setCopyButtonState(button, 'error')
  }

  window.setTimeout(() => {
    button.disabled = false
    setCopyButtonState(button, 'idle')
  }, 1800)
}

function initCopyMarkdownAction(root = document) {
  const contentInner = root.querySelector('article.md-content__inner')
  if (!contentInner || contentInner.querySelector(COPY_BUTTON_SELECTOR)) {
    return
  }

  const action = document.createElement('div')
  action.className = 'md-content__button'

  const button = document.createElement('button')
  button.type = 'button'
  button.className = 'pydantic-copy-markdown-button'
  button.dataset.pydanticCopyMarkdown = 'true'
  button.innerHTML = `
    <span class="md-icon pydantic-copy-markdown-icon" aria-hidden="true">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
        <path d="M19 21H8V7h11m0-2H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2m-3-4H4a2 2 0 0 0-2 2v14h2V3h12z"/>
      </svg>
    </span>
    <span class="pydantic-copy-markdown-label"></span>
  `
  setCopyButtonState(button, 'idle')

  button.addEventListener('click', async () => {
    await copyPageMarkdown(button)
  })

  action.append(button)
  contentInner.prepend(action)
}

if (typeof document$ !== 'undefined') {
  document$.subscribe((root) => {
    initCopyMarkdownAction(root)
  })
} else {
  document.addEventListener('DOMContentLoaded', () => {
    initCopyMarkdownAction(document)
  })
}
