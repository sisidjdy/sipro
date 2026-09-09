"""Backend API Testing for Phase 28b - Site Plan + Photos + Public Showroom

Tests:
1. Photo upload to object storage
2. Field diary with multiple photos
3. Punch list with photos and unit linkage
4. Punch status update with fix photos
5. Unit editing (luas_tanah, luas_bangunan, orientation, corner)
6. Site plan with days_on_market and price_per_m2
7. Showroom public configuration
8. Public showroom endpoint (no auth)
9. Public lead capture with deduplication
10. Portal site plan and progress photos
"""
import io
import sys
import time
import requests

BASE_URL = "https://sipro-frontend-lint.preview.emergentagent.com"
API_URL = f"{BASE_URL}/api"
PASSWORD = "Sipro#2026"

class Phase28bTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.token = None
        self.project_id = None
        self.unit_id = None
        self.showroom_token = None
        
    def log(self, msg, status="INFO"):
        print(f"[{status}] {msg}")
        
    def test(self, name, condition, details=""):
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            self.log(f"✅ {name}", "PASS")
            return True
        else:
            self.log(f"❌ {name} - {details}", "FAIL")
            return False
    
    def login(self, email):
        """Login and get access token"""
        try:
            r = requests.post(f"{API_URL}/auth/login", 
                            json={"email": email, "password": PASSWORD},
                            timeout=15)
            if r.status_code == 200:
                self.token = r.json()["access_token"]
                self.log(f"Logged in as {email}")
                return True
            else:
                self.log(f"Login failed: {r.status_code} {r.text[:200]}", "ERROR")
                return False
        except Exception as e:
            self.log(f"Login error: {str(e)}", "ERROR")
            return False
    
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}
    
    def make_test_image(self, label="Test Photo"):
        """Create a small test PNG image"""
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (480, 300), (100, 150, 200))
            d = ImageDraw.Draw(img)
            d.rectangle([20, 20, 460, 280], outline=(255, 255, 255), width=3)
            d.text((40, 140), label, fill=(255, 255, 255))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            # Fallback: minimal PNG
            import base64
            return base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    
    def test_photo_upload(self):
        """Test 1: Upload photo to object storage"""
        self.log("\n=== Test 1: Photo Upload ===")
        try:
            img_data = self.make_test_image("Diary Photo 1")
            files = {"file": ("test_diary.png", io.BytesIO(img_data), "image/png")}
            data = {"owner_type": "site_diary", "owner_id": self.project_id}
            
            r = requests.post(f"{API_URL}/files/upload", 
                            headers=self.headers(),
                            files=files, data=data, timeout=30)
            
            if self.test("Photo upload returns 200", r.status_code == 200, r.text[:200]):
                result = r.json()
                file_id = result.get("data", {}).get("id")
                self.test("Photo upload returns file_id", bool(file_id), f"file_id={file_id}")
                return file_id
            return None
        except Exception as e:
            self.test("Photo upload", False, str(e))
            return None
    
    def test_field_diary_photos(self, file_ids):
        """Test 2: Create field diary with multiple photos"""
        self.log("\n=== Test 2: Field Diary with Photos ===")
        try:
            payload = {
                "project_id": self.project_id,
                "work_description": "Test diary with multiple photos",
                "weather": "cerah",
                "workforce": 10,
                "photos": file_ids
            }
            
            r = requests.post(f"{API_URL}/field/diary",
                            headers=self.headers(),
                            json=payload, timeout=20)
            
            if self.test("Create diary returns 200", r.status_code == 200, r.text[:200]):
                result = r.json().get("data", {})
                saved_photos = result.get("photos", [])
                self.test("Diary saves photos array", 
                         len(saved_photos) == len(file_ids),
                         f"saved={len(saved_photos)}, sent={len(file_ids)}")
                return True
            return False
        except Exception as e:
            self.test("Create diary with photos", False, str(e))
            return False
    
    def test_punch_list_with_unit(self, file_id):
        """Test 3: Create punch list with unit linkage and photo"""
        self.log("\n=== Test 3: Punch List with Unit & Photo ===")
        try:
            payload = {
                "project_id": self.project_id,
                "unit_id": self.unit_id,
                "title": "Test punch item with photo",
                "severity": "medium",
                "category": "finishing",
                "photos": [file_id]
            }
            
            r = requests.post(f"{API_URL}/field/punchlist",
                            headers=self.headers(),
                            json=payload, timeout=20)
            
            if self.test("Create punch returns 200", r.status_code == 200, r.text[:200]):
                result = r.json().get("data", {})
                punch_id = result.get("id")
                saved_unit = result.get("unit_id")
                saved_photos = result.get("photos", [])
                
                self.test("Punch saves unit_id", saved_unit == self.unit_id,
                         f"saved={saved_unit}, expected={self.unit_id}")
                self.test("Punch saves photos", len(saved_photos) > 0,
                         f"photos={len(saved_photos)}")
                return punch_id
            return None
        except Exception as e:
            self.test("Create punch with unit", False, str(e))
            return None
    
    def test_punch_fix_photos(self, punch_id, file_id):
        """Test 4: Update punch status with fix photos"""
        self.log("\n=== Test 4: Punch Fix Photos ===")
        try:
            payload = {
                "status": "closed",
                "photos": [file_id],
                "note": "Fixed and verified"
            }
            
            r = requests.post(f"{API_URL}/field/punchlist/{punch_id}/status",
                            headers=self.headers(),
                            json=payload, timeout=20)
            
            if self.test("Update punch status returns 200", r.status_code == 200, r.text[:200]):
                result = r.json().get("data", {})
                fix_photos = result.get("fix_photos", [])
                status = result.get("status")
                
                self.test("Punch status updated", status == "closed", f"status={status}")
                self.test("Fix photos saved", len(fix_photos) > 0, f"fix_photos={len(fix_photos)}")
                return True
            return False
        except Exception as e:
            self.test("Update punch with fix photos", False, str(e))
            return False
    
    def test_unit_editing(self):
        """Test 5: Edit unit with luas, orientation, corner"""
        self.log("\n=== Test 5: Unit Editing ===")
        try:
            payload = {
                "luas_tanah": 150,
                "luas_bangunan": 60,
                "orientation": "timur",
                "corner": True
            }
            
            r = requests.put(f"{API_URL}/projects/{self.project_id}/units/{self.unit_id}",
                           headers=self.headers(),
                           json=payload, timeout=20)
            
            if self.test("Update unit returns 200", r.status_code == 200, r.text[:200]):
                result = r.json().get("data", {})
                self.test("Luas tanah saved", result.get("luas_tanah") == 150)
                self.test("Luas bangunan saved", result.get("luas_bangunan") == 60)
                self.test("Orientation saved", result.get("orientation") == "timur")
                self.test("Corner flag saved", result.get("corner") == True)
                return True
            return False
        except Exception as e:
            self.test("Update unit fields", False, str(e))
            return False
    
    def test_invalid_orientation(self):
        """Test 6: Invalid orientation should be rejected"""
        self.log("\n=== Test 6: Invalid Orientation ===")
        try:
            payload = {"orientation": "sebelah kanan"}
            
            r = requests.put(f"{API_URL}/projects/{self.project_id}/units/{self.unit_id}",
                           headers=self.headers(),
                           json=payload, timeout=20)
            
            self.test("Invalid orientation rejected with 400", 
                     r.status_code == 400,
                     f"status={r.status_code}")
            self.test("Error message in Indonesian",
                     "Orientasi" in r.text or "orientasi" in r.text,
                     r.text[:200])
            return True
        except Exception as e:
            self.test("Invalid orientation validation", False, str(e))
            return False
    
    def test_site_plan_metrics(self):
        """Test 7: Site plan returns days_on_market and price_per_m2"""
        self.log("\n=== Test 7: Site Plan Metrics ===")
        try:
            r = requests.get(f"{API_URL}/site-plan/{self.project_id}",
                           headers=self.headers(), timeout=20)
            
            if self.test("Get site plan returns 200", r.status_code == 200, r.text[:200]):
                result = r.json().get("data", {})
                units = result.get("units", [])
                plan = result.get("plan", {})
                
                self.test("Site plan has units", len(units) > 0, f"units={len(units)}")
                
                if units:
                    unit = units[0]
                    self.test("Unit has days_on_market", "days_on_market" in unit,
                             f"keys={list(unit.keys())[:10]}")
                    self.test("Unit has price_per_m2", "price_per_m2" in unit)
                    
                self.test("Plan has shapes (auto-generated)", 
                         bool(plan.get("shapes")),
                         f"shapes={len(plan.get('shapes', []))}")
                return True
            return False
        except Exception as e:
            self.test("Get site plan metrics", False, str(e))
            return False
    
    def test_showroom_config(self):
        """Test 8: Configure public showroom"""
        self.log("\n=== Test 8: Showroom Configuration ===")
        try:
            payload = {
                "enabled": True,
                "headline": "Test Showroom - Phase 28b",
                "contact_wa": "081234567890",
                "show_price": True
            }
            
            r = requests.post(f"{API_URL}/site-plan/{self.project_id}/showroom",
                            headers=self.headers(),
                            json=payload, timeout=20)
            
            if self.test("Configure showroom returns 200", r.status_code == 200, r.text[:200]):
                result = r.json().get("data", {})
                self.showroom_token = result.get("token")
                path = result.get("path")
                
                self.test("Showroom token generated", bool(self.showroom_token),
                         f"token={self.showroom_token}")
                self.test("Showroom path correct", 
                         path == f"/showroom/{self.showroom_token}",
                         f"path={path}")
                return True
            return False
        except Exception as e:
            self.test("Configure showroom", False, str(e))
            return False
    
    def test_public_showroom(self):
        """Test 9: Access public showroom without auth"""
        self.log("\n=== Test 9: Public Showroom (No Auth) ===")
        try:
            # NO Authorization header - public endpoint
            r = requests.get(f"{API_URL}/public/showroom/{self.showroom_token}",
                           timeout=20)
            
            if self.test("Public showroom returns 200", r.status_code == 200, r.text[:200]):
                result = r.json().get("data", {})
                units = result.get("units", [])
                labels = result.get("labels", {})
                project = result.get("project", {})
                
                self.test("Showroom has units", len(units) > 0, f"units={len(units)}")
                self.test("Showroom has SSOT labels", len(labels) > 0, f"labels={list(labels.keys())}")
                self.test("Showroom has project info", bool(project.get("name")))
                
                # Check no sensitive data
                raw_text = r.text.lower()
                self.test("No buyer data in response", 
                         "buyer" not in raw_text and "deal_id" not in raw_text,
                         "Sensitive data found!")
                
                if units:
                    unit = units[0]
                    self.test("Unit has required fields",
                             all(k in unit for k in ["code", "type", "luas_tanah", "price", "status"]))
                return True
            return False
        except Exception as e:
            self.test("Access public showroom", False, str(e))
            return False
    
    def test_lead_capture(self):
        """Test 10: Public lead capture with deduplication"""
        self.log("\n=== Test 10: Lead Capture & Deduplication ===")
        try:
            # Generate unique phone for this test run
            test_phone = f"08129{int(time.time()) % 100000:05d}"
            
            payload = {
                "name": "Test Lead Phase 28b",
                "phone": test_phone,
                "message": "Testing lead capture"
            }
            
            # First submission
            r1 = requests.post(f"{API_URL}/public/showroom/{self.showroom_token}/lead",
                             json=payload, timeout=20)
            
            if self.test("Lead capture returns 200", r1.status_code == 200, r1.text[:200]):
                result1 = r1.json().get("data", {})
                self.test("Lead capture successful", result1.get("ok") == True)
                
                # Second submission with same phone - should detect duplicate
                r2 = requests.post(f"{API_URL}/public/showroom/{self.showroom_token}/lead",
                                 json=payload, timeout=20)
                
                if self.test("Duplicate submission returns 200", r2.status_code == 200):
                    result2 = r2.json().get("data", {})
                    self.test("Duplicate detected", result2.get("duplicate") == True,
                             f"duplicate={result2.get('duplicate')}")
                
                # Verify lead in pipeline
                r3 = requests.get(f"{API_URL}/leads",
                               headers=self.headers(),
                               params={"source": "showroom_public"},
                               timeout=20)
                
                if r3.status_code == 200:
                    leads = r3.json().get("data", [])
                    matching = [l for l in leads if test_phone[-8:] in str(l.get("phone", ""))]
                    self.test("Lead found in pipeline", len(matching) == 1,
                             f"found={len(matching)} leads")
                    
                    if matching:
                        lead = matching[0]
                        self.test("Lead has assigned_to", bool(lead.get("assigned_to")))
                        self.test("Lead has score", bool(lead.get("score")))
                        self.test("Lead has score_band", bool(lead.get("score_band")))
                
                return True
            return False
        except Exception as e:
            self.test("Lead capture and deduplication", False, str(e))
            return False
    
    def test_honeypot(self):
        """Test 11: Honeypot field rejects bots"""
        self.log("\n=== Test 11: Honeypot Protection ===")
        try:
            payload = {
                "name": "Bot Test",
                "phone": "081234567890",
                "website": "http://spam.example"  # Honeypot field
            }
            
            r = requests.post(f"{API_URL}/public/showroom/{self.showroom_token}/lead",
                            json=payload, timeout=20)
            
            self.test("Honeypot rejects with 400", r.status_code == 400,
                     f"status={r.status_code}")
            return True
        except Exception as e:
            self.test("Honeypot protection", False, str(e))
            return False
    
    def test_portal_photos(self):
        """Test 12: Portal buyer can access photos"""
        self.log("\n=== Test 12: Portal Photos ===")
        try:
            # Login as portal buyer
            r1 = requests.post(f"{API_URL}/portal/auth/request-otp",
                             json={"identifier": "+628121111111"},
                             timeout=20)
            
            if r1.status_code == 200:
                r2 = requests.post(f"{API_URL}/portal/auth/verify-otp",
                               json={"identifier": "+628121111111", "code": "000000"},
                               timeout=20)
                
                if self.test("Portal login successful", r2.status_code == 200, r2.text[:200]):
                    portal_token = r2.json().get("token")
                    portal_headers = {"Authorization": f"Bearer {portal_token}"}
                    
                    # Get portal progress with photos
                    r3 = requests.get(f"{API_URL}/portal/progress",
                                    headers=portal_headers, timeout=20)
                    
                    if self.test("Portal progress returns 200", r3.status_code == 200):
                        progress = r3.json().get("data", [])
                        photos = [p for row in progress for p in row.get("photos", [])]
                        self.test("Portal has photos", len(photos) > 0, f"photos={len(photos)}")
                        
                        # Try to access a photo
                        if photos:
                            file_id = photos[0].get("file_id")
                            if file_id:
                                r4 = requests.get(f"{API_URL}/portal/files/{file_id}?auth={portal_token}",
                                                timeout=20)
                                self.test("Portal photo accessible",
                                         r4.status_code == 200 and "image" in r4.headers.get("content-type", ""),
                                         f"status={r4.status_code}, type={r4.headers.get('content-type')}")
                    
                    # Get portal site plan
                    r5 = requests.get(f"{API_URL}/portal/site-plan",
                                    headers=portal_headers, timeout=20)
                    
                    if self.test("Portal site plan returns 200", r5.status_code == 200):
                        sp_data = r5.json().get("data", {})
                        projects = sp_data.get("projects", [])
                        self.test("Portal has projects", len(projects) > 0)
                        
                        if projects:
                            units = projects[0].get("units", [])
                            mine = [u for u in units if u.get("mine")]
                            others = [u for u in units if not u.get("mine")]
                            
                            self.test("Portal marks own units", len(mine) > 0, f"mine={len(mine)}")
                            if others:
                                self.test("Portal hides neighbor prices",
                                         all(u.get("price") is None for u in others))
                    
                    return True
            return False
        except Exception as e:
            self.test("Portal photos access", False, str(e))
            return False
    
    def run_all_tests(self):
        """Run all Phase 28b tests"""
        print("\n" + "="*70)
        print("PHASE 28b BACKEND API TESTING")
        print("="*70)
        
        # Login as owner
        if not self.login("owner@sipro.co.id"):
            self.log("Cannot proceed without login", "ERROR")
            return False
        
        # Get project and unit IDs
        try:
            r = requests.get(f"{API_URL}/projects", headers=self.headers(), timeout=15)
            if r.status_code == 200:
                projects = r.json().get("data", [])
                if projects:
                    self.project_id = projects[0]["id"]
                    self.log(f"Using project: {self.project_id}")
                    
                    # Get first unit
                    r2 = requests.get(f"{API_URL}/site-plan/{self.project_id}",
                                    headers=self.headers(), timeout=20)
                    if r2.status_code == 200:
                        units = r2.json().get("data", {}).get("units", [])
                        if units:
                            self.unit_id = units[0]["id"]
                            self.log(f"Using unit: {self.unit_id}")
        except Exception as e:
            self.log(f"Setup error: {str(e)}", "ERROR")
            return False
        
        if not self.project_id or not self.unit_id:
            self.log("Cannot get project/unit IDs", "ERROR")
            return False
        
        # Run tests
        file_id1 = self.test_photo_upload()
        file_id2 = self.test_photo_upload()
        
        if file_id1 and file_id2:
            self.test_field_diary_photos([file_id1, file_id2])
        
        file_id3 = self.test_photo_upload()
        if file_id3:
            punch_id = self.test_punch_list_with_unit(file_id3)
            
            file_id4 = self.test_photo_upload()
            if punch_id and file_id4:
                self.test_punch_fix_photos(punch_id, file_id4)
        
        self.test_unit_editing()
        self.test_invalid_orientation()
        self.test_site_plan_metrics()
        self.test_showroom_config()
        
        if self.showroom_token:
            self.test_public_showroom()
            self.test_lead_capture()
            self.test_honeypot()
        
        self.test_portal_photos()
        
        # Summary
        print("\n" + "="*70)
        print(f"RESULTS: {self.tests_passed}/{self.tests_run} PASSED")
        print("="*70)
        
        return self.tests_passed == self.tests_run

if __name__ == "__main__":
    tester = Phase28bTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
