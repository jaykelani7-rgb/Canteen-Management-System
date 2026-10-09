import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import AppErrorBoundary from '../../src/components/AppErrorBoundary';
import '../../src/index.css';
import './student.css';
import { registerStudentPwa } from './pwa';
import { initializeStudentNative } from './native';
import NativeBackendNotice from './NativeBackendNotice';

const placeholder = import.meta.env.VITE_NATIVE_APP === 'true' && import.meta.env.VITE_ANDROID_BACKEND_PLACEHOLDER === 'true';

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><AppErrorBoundary><div className={placeholder ? "native-staging-shell" : undefined}>{placeholder && <NativeBackendNotice />}<App /></div></AppErrorBoundary></React.StrictMode>);
registerStudentPwa();

requestAnimationFrame(() => { void initializeStudentNative(); });
