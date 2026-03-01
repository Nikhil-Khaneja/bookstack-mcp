import { useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { createBook, clearError } from '../features/booksSlice'

function CreateBook() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const error = useSelector(state => state.books.error)

  const [form, setForm] = useState({
    title: '',
    isbn: '',
    publication_year: '',
    available_copies: 1,
    author_id: '',
  })

  const [successMsg, setSuccessMsg] = useState('')

  function handleChange(e) {
    setForm({ ...form, [e.target.name]: e.target.value })
  }

  async function handleSubmit(e) {
    e.preventDefault()
    dispatch(clearError())

    const result = await dispatch(
      createBook({
        ...form,
        publication_year: parseInt(form.publication_year),
        available_copies: parseInt(form.available_copies),
        author_id: parseInt(form.author_id),
      })
    )

    if (createBook.fulfilled.match(result)) {
      setSuccessMsg(`Book "${result.payload.title}" created successfully!`)
      setForm({ title: '', isbn: '', publication_year: '', available_copies: 1, author_id: '' })
      // Redirect to home after 1.5 seconds so user sees the updated list
      setTimeout(() => navigate('/'), 1500)
    }
  }

  return (
    <div className="form-card">
      <h2>Add New Book</h2>

      {error && <p className="error-msg">{error}</p>}
      {successMsg && <p className="success-msg">{successMsg}</p>}

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Title</label>
          <input
            type="text"
            name="title"
            value={form.title}
            onChange={handleChange}
            placeholder="e.g. The Great Gatsby"
            required
          />
        </div>

        <div className="form-group">
          <label>ISBN</label>
          <input
            type="text"
            name="isbn"
            value={form.isbn}
            onChange={handleChange}
            placeholder="e.g. 9780743273565"
            required
          />
        </div>

        <div className="form-group">
          <label>Publication Year</label>
          <input
            type="number"
            name="publication_year"
            value={form.publication_year}
            onChange={handleChange}
            placeholder="e.g. 1925"
            required
          />
        </div>

        <div className="form-group">
          <label>Available Copies</label>
          <input
            type="number"
            name="available_copies"
            value={form.available_copies}
            onChange={handleChange}
            min="0"
          />
        </div>

        <div className="form-group">
          <label>Author ID</label>
          <input
            type="number"
            name="author_id"
            value={form.author_id}
            onChange={handleChange}
            placeholder="e.g. 1"
            required
          />
        </div>

        <button type="submit" className="btn-primary">Create Book</button>
      </form>
    </div>
  )
}

export default CreateBook
