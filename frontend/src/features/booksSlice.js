import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'
import axios from 'axios'

const API_BASE = 'http://localhost:8000'

// ─────────────────────── Async Thunks (Axios) ──────────────────────────

// GET /books — fetch all books from the API
export const fetchBooks = createAsyncThunk(
  'books/fetchBooks',
  async (_, { rejectWithValue }) => {
    try {
      const response = await axios.get(`${API_BASE}/books/?skip=0&limit=100`)
      return response.data
    } catch (error) {
      return rejectWithValue(error.response?.data?.detail || 'Failed to fetch books')
    }
  }
)

// POST /books — create a new book
export const createBook = createAsyncThunk(
  'books/createBook',
  async (bookData, { rejectWithValue }) => {
    try {
      const response = await axios.post(`${API_BASE}/books/`, bookData)
      return response.data
    } catch (error) {
      return rejectWithValue(error.response?.data?.detail || 'Failed to create book')
    }
  }
)

// PUT /books/{id} — update an existing book
export const updateBook = createAsyncThunk(
  'books/updateBook',
  async ({ id, ...bookData }, { rejectWithValue }) => {
    try {
      const response = await axios.put(`${API_BASE}/books/${id}`, bookData)
      return response.data
    } catch (error) {
      return rejectWithValue(error.response?.data?.detail || 'Failed to update book')
    }
  }
)

// DELETE /books/{id} — delete a book
export const deleteBook = createAsyncThunk(
  'books/deleteBook',
  async (id, { rejectWithValue }) => {
    try {
      await axios.delete(`${API_BASE}/books/${id}`)
      return id  // return the id so we can filter it out of state
    } catch (error) {
      return rejectWithValue(error.response?.data?.detail || 'Failed to delete book')
    }
  }
)

// ─────────────────────────── Slice ─────────────────────────────────────

const initialState = {
  items: [],      // list of book objects from the API
  status: 'idle', // 'idle' | 'loading' | 'succeeded' | 'failed'
  error: null,    // error message string
}

const booksSlice = createSlice({
  name: 'books',
  initialState,
  reducers: {
    clearError(state) {
      state.error = null
    },
  },
  extraReducers: (builder) => {
    builder
      // ── fetchBooks ──────────────────────────────────────────────────
      .addCase(fetchBooks.pending, (state) => {
        state.status = 'loading'
        state.error = null
      })
      .addCase(fetchBooks.fulfilled, (state, action) => {
        state.status = 'succeeded'
        state.items = action.payload
      })
      .addCase(fetchBooks.rejected, (state, action) => {
        state.status = 'failed'
        state.error = action.payload
      })

      // ── createBook ──────────────────────────────────────────────────
      .addCase(createBook.fulfilled, (state, action) => {
        state.items.push(action.payload)
      })
      .addCase(createBook.rejected, (state, action) => {
        state.error = action.payload
      })

      // ── updateBook ──────────────────────────────────────────────────
      .addCase(updateBook.fulfilled, (state, action) => {
        const index = state.items.findIndex(b => b.id === action.payload.id)
        if (index !== -1) {
          state.items[index] = action.payload
        }
      })
      .addCase(updateBook.rejected, (state, action) => {
        state.error = action.payload
      })

      // ── deleteBook ──────────────────────────────────────────────────
      .addCase(deleteBook.fulfilled, (state, action) => {
        state.items = state.items.filter(b => b.id !== action.payload)
      })
      .addCase(deleteBook.rejected, (state, action) => {
        state.error = action.payload
      })
  },
})

export const { clearError } = booksSlice.actions
export default booksSlice.reducer
