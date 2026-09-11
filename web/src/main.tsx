import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { Landing } from './components/Landing'
import './index.css'

// Two routes is not worth a router dependency. The server serves the SPA for any
// path, so the pathname is the only thing that decides which one mounts.
const onConsole = window.location.pathname.startsWith('/console')

createRoot(document.getElementById('root')!).render(
  <StrictMode>{onConsole ? <App /> : <Landing />}</StrictMode>,
)
