import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Home from './pages/Home'
import CreateBook from './pages/CreateBook'
import UpdateBook from './pages/UpdateBook'
import Ai from './pages/Ai'
import Architecture from './pages/Architecture'

function App() {
  return (
    <Router>
      <Navbar />
      <div className="container">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/create" element={<CreateBook />} />
          <Route path="/update/:id" element={<UpdateBook />} />
          <Route path="/ai" element={<Ai />} />
          <Route path="/architecture" element={<Architecture />} />
        </Routes>
      </div>
    </Router>
  )
}

export default App
