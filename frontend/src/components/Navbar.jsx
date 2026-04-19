import { Link } from 'react-router-dom'

function Navbar() {
  return (
    <nav>
      <span className="brand">📚 Library Manager</span>
      <Link to="/">Home</Link>
      <Link to="/create">Add Book</Link>
      <Link to="/ai">AI Console</Link>
      <Link to="/architecture">Architecture</Link>
    </nav>
  )
}

export default Navbar
