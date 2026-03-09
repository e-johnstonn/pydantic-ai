const COPY_MARKDOWN_LABELS = {
  idle: 'Copy page',
  pending: 'Copying...',
  success: 'Copied!',
  error: 'Copy failed',
}

const COPY_BUTTON_SELECTOR = '[data-pydantic-copy-markdown-url]'

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
    const markdownUrl = button.dataset.pydanticCopyMarkdownUrl
    if (!markdownUrl) {
      throw new Error('Missing markdown URL')
    }

    const response = await fetch(markdownUrl)
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
  for (const button of root.querySelectorAll(COPY_BUTTON_SELECTOR)) {
    if (button.dataset.pydanticCopyMarkdownBound === 'true') {
      continue
    }

    button.dataset.pydanticCopyMarkdownBound = 'true'
    setCopyButtonState(button, 'idle')
    button.addEventListener('click', async () => {
      await copyPageMarkdown(button)
    })
  }
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
