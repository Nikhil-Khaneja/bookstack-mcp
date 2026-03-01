import { useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { Link, useNavigate } from 'react-router-dom'
import { fetchBooks, deleteBook } from '../features/booksSlice'

function Home() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { items: books, status, error } = useSelector(state => state.books)

  // Fetch all books when the page loads
  useEffect(() => {
    dispatch(fetchBooks())
  }, [dispatch])

  // Delete a book and update Redux state automatically
  async function handleDelete(book) {
    const confirmed = window.confirm(`Delete "${book.title}"? This cannot be undone.`)
    if (!confirmed) return
    dispatch(deleteBook(book.id))
  }

  if (status === 'loading') {
    return <p className="loading">Loading books...</p>
  }

  if (status === 'failed') {
    return <p className="error-msg">Error: {error}</p>
  }

  return (
    <div>
      <h1 className="page-title">All Books</h1>

      {books.length === 0 ? (
        <p className="loading">No books found. <Link to="/create">Add one!</Link></p>
      ) : (
        books.map(book => (
          <div className="card" key={book.id}>
            <div>
              <h3>{book.title}</h3>
              <p><strong>Author:</strong> {book.author.first_name} {book.author.last_name}</p>
              <p><strong>ISBN:</strong> {book.isbn}</p>
              <p><strong>Year:</strong> {book.publication_year}</p>
              <p><strong>Copies Available:</strong> {book.available_copies}</p>
            </div>

            <div className="card-actions">
              <button
                className="btn-secondary"
                onClick={() => navigate(`/update/${book.id}`)}
              >
                Edit
              </button>
              <button
                className="btn-danger"
                onClick={() => handleDelete(book)}
              >
                Delete
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  )
}

export default Home
