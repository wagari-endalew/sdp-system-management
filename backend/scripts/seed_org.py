"""
Seed script: creates the initial Director / Team Leader hierarchy so the
registration dropdowns aren't empty when testing Team Leader/Employee signup.

Creates exactly 4 Directors (these appear in the Director dropdown when
someone registers as Team Leader):
  1. የካዳስተር ምዝገባ አገልግሎት ዳይሬክቶሬት ዳይሬክተር
  2. የተቀናጀ የመሬት መረጃና አርካይቭ ዲጂታይዜሽን ዳይሬክተር
  3. ኢንፎርሜሽን ቴክኖሎጂ ዳይሬክቶሬት ዳይሬክተር
  4. የይዞታ ማረጋገጥና የአድራሻ ሥርዓት ዳይሬክቶሬት ዳይሬክተር

And exactly 6 Team Leaders (these appear in the Team Leader dropdown when
someone registers as Employee):
  1. የመረጃና ዲጂታላይዜሽን ቡድን መሪ
  2. የመሬት ይዞታ አረጋጋጭ ቡድን መሪ
  3. የአድራሻ ዝርጋታና አስተዳደር ቡድን መሪ
  4. ቋሚ ንብረት ምዝገባና አገልግሎት ቡድን መሪ
  5. የካዳስተር አገልግሎት ቡድን መሪ
  6. ክርክር መዝገብ አረጋጋጭ ቡድን መሪ

Team Leader registration requires a real Director to report to (enforced by
the backend, not optional) — the list you gave didn't specify who reports to
whom, so each Team Leader below is assigned to the topically closest
Director as a reasonable default. Check/edit TEAM_LEADERS below if these
pairings aren't what you want; they're easy to change before re-running.

All accounts are created ACTIVE (registration no longer requires Super Admin
approval for any role), with a shared temporary password — change it after
first login. Safe to re-run: skips any account whose email already exists.

Note: this supersedes the Directors/Team Leaders from earlier versions of
this script. It never deletes anything, so if you ran an older version,
those accounts are still in the database — deactivate or delete them
manually from Users if you want exactly this list and nothing else.

Usage (from backend/):
    python3 -m scripts.seed_org
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.core.database import Base, engine, AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole, UserStatus

SEED_PASSWORD = "Passw0rd!"  # change after first login

DIRECTORS = [
    dict(  # index 0
        full_name="የካዳስተር ምዝገባ አገልግሎት ዳይሬክቶሬት ዳይሬክተር",
        username="director_cadastre_registration",
        email="director.cadastreregistration@sdp.local",
        position="የካዳስተር ምዝገባ አገልግሎት ዳይሬክቶሬት ዳይሬክተር",
    ),
    dict(  # index 1
        full_name="የተቀናጀ የመሬት መረጃና አርካይቭ ዲጂታይዜሽን ዳይሬክተር",
        username="director_land_info_digitalization",
        email="director.landinfodigitalization@sdp.local",
        position="የተቀናጀ የመሬት መረጃና አርካይቭ ዲጂታይዜሽን ዳይሬክተር",
    ),
    dict(  # index 2
        full_name="ኢንፎርሜሽን ቴክኖሎጂ ዳይሬክቶሬት ዳይሬክተር",
        username="director_information_technology",
        email="director.informationtechnology@sdp.local",
        position="ኢንፎርሜሽን ቴክኖሎጂ ዳይሬክቶሬት ዳይሬክተር",
    ),
    dict(  # index 3
        full_name="የይዞታ ማረጋገጥና የአድራሻ ሥርዓት ዳይሬክቶሬት ዳይሬክተር",
        username="director_holding_address_system",
        email="director.holdingaddresssystem@sdp.local",
        position="የይዞታ ማረጋገጥና የአድራሻ ሥርዓት ዳይሬክቶሬት ዳይሬክተር",
    ),
]

# (team leader fields, index of the director in DIRECTORS they report to)
# — topical best-guess pairing; edit freely, see note above.
TEAM_LEADERS = [
    (
        dict(
            full_name="የመረጃና ዲጂታላይዜሽን ቡድን መሪ",
            username="teamlead_info_digitalization",
            email="teamlead.infodigitalization@sdp.local",
            position="የመረጃና ዲጂታላይዜሽን ቡድን መሪ",
        ),
        1,  # → የተቀናጀ የመሬት መረጃና አርካይቭ ዲጂታይዜሽን ዳይሬክተር
    ),
    (
        dict(
            full_name="የመሬት ይዞታ አረጋጋጭ ቡድን መሪ",
            username="teamlead_landholding_verification",
            email="teamlead.landholdingverification@sdp.local",
            position="የመሬት ይዞታ አረጋጋጭ ቡድን መሪ",
        ),
        3,  # → የይዞታ ማረጋገጥና የአድራሻ ሥርዓት ዳይሬክቶሬት ዳይሬክተር
    ),
    (
        dict(
            full_name="የአድራሻ ዝርጋታና አስተዳደር ቡድን መሪ",
            username="teamlead_address_administration",
            email="teamlead.addressadministration@sdp.local",
            position="የአድራሻ ዝርጋታና አስተዳደር ቡድን መሪ",
        ),
        3,  # → የይዞታ ማረጋገጥና የአድራሻ ሥርዓት ዳይሬክቶሬት ዳይሬክተር
    ),
    (
        dict(
            full_name="ቋሚ ንብረት ምዝገባና አገልግሎት ቡድን መሪ",
            username="teamlead_fixed_asset_registration",
            email="teamlead.fixedassetregistration@sdp.local",
            position="ቋሚ ንብረት ምዝገባና አገልግሎት ቡድን መሪ",
        ),
        0,  # → የካዳስተር ምዝገባ አገልግሎት ዳይሬክቶሬት ዳይሬክተር
    ),
    (
        dict(
            full_name="የካዳስተር አገልግሎት ቡድን መሪ",
            username="teamlead_cadastre_service",
            email="teamlead.cadastreservice@sdp.local",
            position="የካዳስተር አገልግሎት ቡድን መሪ",
        ),
        0,  # → የካዳስተር ምዝገባ አገልግሎት ዳይሬክቶሬት ዳይሬክተር
    ),
    (
        dict(
            full_name="ክርክር መዝገብ አረጋጋጭ ቡድን መሪ",
            username="teamlead_dispute_record_verification",
            email="teamlead.disputerecordverification@sdp.local",
            position="ክርክር መዝገብ አረጋጋጭ ቡድን መሪ",
        ),
        0,  # → የካዳስተር ምዝገባ አገልግሎት ዳይሬክቶሬት ዳይሬክተር (land dispute records relate to registration)
    ),
]


async def get_or_create(session, **fields) -> tuple[User, bool]:
    existing = await session.execute(select(User).where(User.email == fields["email"]))
    user = existing.scalar_one_or_none()
    if user:
        return user, False
    user = User(**fields, password_hash=hash_password(SEED_PASSWORD), status=UserStatus.ACTIVE)
    session.add(user)
    await session.flush()
    return user, True


async def seed_org_hierarchy(session, log=lambda *a: None) -> None:
    """Core seeding logic, reusable both by this standalone script and by
    the app's own startup hook (see app/main.py) so a fresh deployment gets
    these Directors/Team Leaders automatically — no manual step to forget."""
    director_rows = []
    for d in DIRECTORS:
        user, created = await get_or_create(session, role=UserRole.DIRECTOR, **d)
        director_rows.append(user)
        log(f"{'Created' if created else 'Already exists'}: Director — {d['full_name']} ({d['email']})")

    for tl, director_idx in TEAM_LEADERS:
        user, created = await get_or_create(
            session,
            role=UserRole.TEAM_LEADER,
            director_id=director_rows[director_idx].id,
            **tl,
        )
        log(f"{'Created' if created else 'Already exists'}: Team Leader — {tl['full_name']} ({tl['email']}) "
            f"reports to {DIRECTORS[director_idx]['full_name']}")

    await session.commit()


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await seed_org_hierarchy(session, log=print)

    print()
    print(f"Done. Shared temporary password for any newly created account: {SEED_PASSWORD}")
    print("Change it after first login — these are meant as starting org data, not permanent credentials.")


if __name__ == "__main__":
    asyncio.run(main())
