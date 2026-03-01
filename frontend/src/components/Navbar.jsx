import { Link } from 'react-router-dom'

function Navbar() {
  return (
    <nav>
      <span className="brand">📚 Library Manager</span>
      <Link to="/">Home</Link>
      <Link to="/create">Add Book</Link>
    </nav>
  )
}

export default Navbar
