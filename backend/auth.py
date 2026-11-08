"""Google OAuth login.

Identity only — this has nothing to do with the app's Anthropic API key,
which stays entirely client-side (localStorage) regardless of login state,
per the app's bring-your-own-key policy. Login just lets a user see their
name/picture in the UI and (optionally, later) their own lesson history.

Requires GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and SESSION_SECRET to be set;
if they aren't, the /auth/* routes are not mounted and the frontend's
"Sign in" button simply won't do anything useful (the app works fine without
login — it's purely additive).
"""

import os

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import RedirectResponse

import db

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()

router = APIRouter()
is_configured = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


@router.get("/api/auth-status")
def auth_status():
    return {"configured": is_configured}

if is_configured:
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    @router.get("/auth/google/login")
    async def google_login(request: Request):
        redirect_uri = str(request.url_for("google_callback"))
        if redirect_uri.startswith("http://") and request.headers.get("x-forwarded-proto") == "https":
            redirect_uri = "https://" + redirect_uri[len("http://"):]
        return await oauth.google.authorize_redirect(request, redirect_uri)

    @router.get("/auth/google/callback", name="google_callback")
    async def google_callback(request: Request):
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get("userinfo")
        if not userinfo:
            raise HTTPException(status_code=400, detail="Google login failed")

        request.session["user"] = {
            "email": userinfo["email"],
            "name": userinfo.get("name"),
            "picture": userinfo.get("picture"),
        }
        db.upsert_user(userinfo["email"], userinfo.get("name"), userinfo.get("picture"))
        return RedirectResponse(url="/")

    @router.post("/auth/logout")
    def logout(request: Request):
        request.session.clear()
        return {"ok": True}

    @router.get("/api/me")
    def me(request: Request):
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="not signed in")
        return user

else:
    @router.get("/api/me")
    def me_unconfigured():
        raise HTTPException(status_code=401, detail="login not configured on this server")
