// ui/src/App.jsx

import React from "react";
import MainLayout from "@/layouts/MainLayout";
import Routes from "./Routes";

/**
 * App
 * ----
 * Root React component.
 *
 * Responsibilities:
 * - Mount the global layout once
 * - Delegate all navigation to Routes
 *
 * NOTE:
 * - Do NOT put page logic, tabs, or API calls here
 * - Header (time, env, branding) lives in MainLayout
 */
export default function App() {
  return (
    <MainLayout>
      <Routes />
    </MainLayout>
  );
}