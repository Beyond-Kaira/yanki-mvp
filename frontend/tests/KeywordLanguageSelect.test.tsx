import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { KeywordLanguageSelect } from '@/components/keywords/KeywordsChrome'

vi.mock('next/navigation', () => ({
  usePathname: () => '/search-visibility/keywords',
}))

describe('KeywordLanguageSelect', () => {
  it('lists every ISO 639-1 language once opened', async () => {
    render(<KeywordLanguageSelect value="en" onChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /^Language:/ }))
    expect(screen.getAllByRole('option').length).toBeGreaterThan(150)
  })

  it('filters on the native name, not just the English one', async () => {
    render(<KeywordLanguageSelect value="en" onChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /^Language:/ }))
    await userEvent.type(screen.getByLabelText('Search language'), 'Türkçe')
    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(1)
    expect(options[0]).toHaveTextContent('Turkish')
  })

  it('falls back to a globe for a language with no region of its own', async () => {
    render(<KeywordLanguageSelect value="en" onChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /^Language:/ }))
    const search = screen.getByLabelText('Search language')
    await userEvent.type(search, 'turkish')
    expect(screen.getByRole('option')).toHaveTextContent('🇹🇷')
    await userEvent.clear(search)
    await userEvent.type(search, 'esperanto')
    expect(screen.getByRole('option')).toHaveTextContent('🌐')
  })

  it('reports the code, not the name, when an option is picked', async () => {
    const onChange = vi.fn()
    render(<KeywordLanguageSelect value="en" onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: /^Language:/ }))
    await userEvent.type(screen.getByLabelText('Search language'), 'german')
    await userEvent.click(within(screen.getByRole('option')).getByRole('button'))
    expect(onChange).toHaveBeenCalledWith('de')
  })

  it('takes the first match on Enter instead of submitting the form around it', async () => {
    const onChange = vi.fn()
    const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault())
    render(
      <form onSubmit={onSubmit}>
        <KeywordLanguageSelect value="en" onChange={onChange} />
      </form>,
    )
    await userEvent.click(screen.getByRole('button', { name: /^Language:/ }))
    await userEvent.type(screen.getByLabelText('Search language'), 'turkish{Enter}')
    expect(onChange).toHaveBeenCalledWith('tr')
    expect(onSubmit).not.toHaveBeenCalled()
  })
})
