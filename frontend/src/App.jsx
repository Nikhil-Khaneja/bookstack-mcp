import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Home from './pages/Home'
import CreateBook from './pages/CreateBook'
import UpdateBook from './pages/UpdateBook'

function App() {
  return (
    <Router>
      <Navbar />
      <div className="container">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/create" element={<CreateBook />} />
          <Route path="/update/:id" element={<UpdateBook />} />
        </Routes>
      </div>
    </Router>
  )
}

export default App
