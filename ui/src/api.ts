// REST calls for user actions that don't go through the model.

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string }).detail ?? `HTTP ${res.status}`);
  return data as T;
}

export interface BookingOption {
  seller: string;
  is_airline: boolean;
  fare_name?: string | null;
  price?: number | null;
  leg: string;
  flight_numbers: string[];
  features: string[];
  baggage: string[];
  booking_url?: string | null;
  booking_post_data?: string | null;
  booking_phone?: string | null;
}

export interface BookingOptions {
  options: BookingOption[];
  fetched_at?: string | null;
  links_valid_minutes: number;
  notes: string[];
}

export type Preferences = Record<string, unknown> & { updated_at?: string | null };

export const api = {
  bookingOptions: (b: { booking_token: string; origin: string; destination: string; date: string; return_date?: string | null }) =>
    request<BookingOptions>("POST", "/api/booking-options", b),
  getPreferences: () => request<Preferences>("GET", "/api/preferences"),
  updatePreferences: (changes: Record<string, unknown>) =>
    request<{ preferences: Preferences; changed: Record<string, unknown>; message: string }>("PUT", "/api/preferences", { changes }),
};

/** Open a seller's page the way Google Flights does: POST the form data to the redirect URL. */
export function openBooking(url: string, postData: string) {
  const form = document.createElement("form");
  form.method = "POST";
  form.action = url;
  form.target = "_blank";
  form.rel = "noopener";
  for (const [k, v] of new URLSearchParams(postData)) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = k;
    input.value = v;
    form.appendChild(input);
  }
  document.body.appendChild(form);
  form.submit();
  form.remove();
}
