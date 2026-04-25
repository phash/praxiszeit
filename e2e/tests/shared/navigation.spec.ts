import { test, expect } from '../../fixtures/base.fixture';

test.describe('Navigation & Access Control', () => {
  test('employee sees no admin links', async ({ employeePage }) => {
    // Employee sidebar/navigation should NOT contain admin links
    await employeePage.goto('/');
    await employeePage.waitForLoadState('networkidle');

    // Scope queries to <nav> so the test is robust against in-page banners
    // like "Buchung fehlt — Zur Zeiterfassung →" on the dashboard, which
    // duplicate the substring "Zeiterfassung" outside the sidebar.
    const sidebar = employeePage.locator('nav').first();

    // Verify employee nav items are visible
    await expect(sidebar.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: 'Zeiterfassung', exact: true })).toBeVisible();

    // Verify admin-only items are NOT visible
    await expect(sidebar.getByRole('link', { name: 'Benutzerverwaltung', exact: true })).not.toBeVisible();
    await expect(sidebar.getByRole('link', { name: 'Berichte', exact: true })).not.toBeVisible();
    // The "Administration" section heading should not exist for employees.
    // Use a strict heading-name check inside the sidebar so we don't
    // accidentally match the word "Administration" in dashboard content.
    await expect(sidebar.getByText('Administration', { exact: true })).not.toBeVisible();
  });

  test('admin pages redirect employee', async ({ employeePage }) => {
    // Try navigating to an admin page as employee
    await employeePage.goto('/admin/users');
    await employeePage.waitForLoadState('networkidle');

    // ProtectedRoute with requiredRole="admin" redirects non-admins to "/"
    await expect(employeePage).toHaveURL('http://localhost/');
  });

  test('admin sees admin navigation', async ({ adminPage }) => {
    await adminPage.goto('/');
    await adminPage.waitForLoadState('networkidle');

    const sidebar = adminPage.locator('nav').first();

    // Admin should see the Administration section and admin nav items
    await expect(sidebar.getByText('Administration', { exact: true })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: 'Benutzerverwaltung', exact: true })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: 'Berichte', exact: true })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: 'Fehler-Monitoring', exact: true })).toBeVisible();
  });

  test('mobile hamburger menu', async ({ employeePage }) => {
    // Set viewport to mobile size (below lg breakpoint = 1024px)
    await employeePage.setViewportSize({ width: 375, height: 667 });
    await employeePage.goto('/');
    await employeePage.waitForLoadState('networkidle');

    // On mobile, the sidebar is hidden (translated off-screen)
    // The nav links inside the sidebar should not be visible initially
    // (sidebar has -translate-x-full on mobile when closed)

    // The hamburger button has aria-label="Menü öffnen"
    const hamburgerButton = employeePage.getByRole('button', { name: 'Menü öffnen' });
    await expect(hamburgerButton).toBeVisible();

    // Click hamburger to open sidebar
    await hamburgerButton.click();

    // After clicking, navigation links should become visible. Scope to <nav>
    // so the dashboard "Buchung fehlt — Zur Zeiterfassung →" banner doesn't
    // produce a strict-mode locator collision.
    const sidebar = employeePage.locator('nav').first();
    await expect(sidebar.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible();
    await expect(sidebar.getByRole('link', { name: 'Zeiterfassung', exact: true })).toBeVisible();
    // Hilfe is a button (opens panel), not a link – check Abmelden button instead
    await expect(employeePage.getByRole('button', { name: 'Abmelden' })).toBeVisible();

    // Close button should be visible (aria-label="Menü schließen")
    const closeButton = employeePage.getByRole('button', { name: 'Menü schließen' });
    await expect(closeButton).toBeVisible();

    // Close the menu
    await closeButton.click();

    // Hamburger should be visible again
    await expect(hamburgerButton).toBeVisible();
  });
});
