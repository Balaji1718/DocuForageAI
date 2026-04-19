import { initializeApp, getApps, getApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyBhOZm4rb5yLooALIw1upA8Akr08WDCGrI",
  authDomain: "docuforge-ai-3171d.firebaseapp.com",
  projectId: "docuforge-ai-3171d",
  storageBucket: "docuforge-ai-3171d.firebasestorage.app",
  messagingSenderId: "555655977736",
  appId: "1:555655977736:web:1550ab4a8242c237ae2abd",
  measurementId: "G-2SW9NTPCKC",
};

export const firebaseApp = getApps().length ? getApp() : initializeApp(firebaseConfig);
export const auth = getAuth(firebaseApp);
export const db = getFirestore(firebaseApp);
