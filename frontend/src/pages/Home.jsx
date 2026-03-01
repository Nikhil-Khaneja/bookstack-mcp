import { useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { Link } from 'react-router-dom'
import { fetchBooks } from '../features/booksSlice'

function Home() {
  const dispatch = useDispatch()
  const { items: books, status, error } = useSelector(state => state.books)

  // Fetch all books when the page loads
  useEffect(() => {
    dispatch(fetchBooks())
  }, [dispatch])

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
          </div>
        ))
      )}
    </div>
  )
}

export default Home
