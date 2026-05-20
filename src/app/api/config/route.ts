import { NextResponse } from "next/server"

export async function GET() {
  const clientId = process.env.AUTH_CLIENT_ID
  const authCenterBaseURL = process.env.AUTH_BASE_URL

  if (!clientId || !authCenterBaseURL) {
    return NextResponse.json(
      { error: "Missing AUTH_CLIENT_ID or AUTH_BASE_URL" },
      { status: 500 }
    )
  }

  return NextResponse.json({ clientId, authCenterBaseURL })
}
