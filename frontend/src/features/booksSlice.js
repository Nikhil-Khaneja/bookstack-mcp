import { createSlice } from '@reduxjs/toolkit'

// Initial state shape for the books slice
const initialState = {
  items: [],      // list of book objects from the API
  status: 'idle', // 'idle' | 'loading' | 'succeeded' | 'failed'
  error: null,    // error message string
}

const booksSlice = createSlice({
  name: 'books',
  initialState,
  reducers: {
    // Set the full list of books
    setBooks(state, action) {
      state.items = action.payload
    },
    // Add one book to the list
    addBook(state, action) {
      state.items.push(action.payload)
    },
    // Replace an updated book in the list
    updateBookInState(state, action) {
      const index = state.items.findIndex(b => b.id === action.payload.id)
      if (index !== -1) {
        state.items[index] = action.payload
      }
    },
    // Remove a book from the list by id
    removeBook(state, action) {
      state.items = state.items.filter(b => b.id !== action.payload)
    },
    setStatus(state, action) {
      state.status = action.payload
    },
    setError(state, action) {
      state.error = action.payload
    },
  },
})

export const { setBooks, addBook, updateBookInState, removeBook, setStatus, setError } =
  booksSlice.actions

export default booksSlice.reducer
