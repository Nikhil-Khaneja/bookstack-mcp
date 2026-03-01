import { useState, useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate, useParams } from 'react-router-dom'
import { updateBook, fetchBooks, clearError } from '../features/booksSlice'

function UpdateBook() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { id } = useParams()  // get book id from URL /update/:id

  const { items: books, error } = useSelector(state => state.books)
  const [successMsg, setSuccessMsg] = useState('')

  const [form, setForm] = useState({
    title: '',
    isbn: '',
    publication_year: '',
    available_copies: '',
    author_id: '',
  })

  // Pre-fill form with existing book data
  useEffect(() => {
    if (books.length === 0) {
      dispatch(fetchBooks())
    }
  }, [dispatch, books.length])

  useEffect(() => {
    const book = books.find(b => b.id === parseInt(id))
    if (book) {
      setForm({
        title: book.title,
        isbn: book.isbn,
        publication_year: book.publication_year,
        available_copies: book.available_copies,
        author_id: book.author_id,
      })
    }
  }, [books, id])

  function handleChange(e) {
    setForm({ ...form, [e.target.name]: e.target.value })
  }

  async function handleSubmit(e) {
    e.preventDefault()
    dispatch(clearError())

    const result = await dispatch(
      updateBook({
        id: parseInt(id),
        title: form.title,
        isbn: form.isbn,
        publication_year: parseInt(form.publication_year),
        available_copies: parseInt(form.available_copies),
        author_id: parseInt(form.author_id),
      })
    )

    if (updateBook.fulfilled.match(result)) {
      setSuccessMsg(`Book updated successfully!`)
      setTimeout(() => navigate('/'), 1500)
    }
  }

  return (
    <div className="form-card">
      <h2>Update Book (ID: {id})</h2>

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
            required
          />
        </div>

        <button type="submit" className="btn-secondary">Update Book</button>
      </form>
    </div>
  )
}

export default UpdateBook
