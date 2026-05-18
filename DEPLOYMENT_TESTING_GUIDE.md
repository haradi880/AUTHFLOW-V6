# DEPLOYMENT & TESTING GUIDE - Phase 1 Security Hardening
**AuthFlow V2 - May 11, 2026**

---

## PRE-DEPLOYMENT CHECKLIST

### 1. Dependencies Installation ✅
```bash
# Install security dependencies
pip install Flask-WTF==1.2.1 Flask-Limiter==3.5.0 python-magic-bin

# Verify installation
pip list | grep -E "Flask-WTF|Flask-Limiter"
```

**Status:** Ready to execute

---

### 2. Database Migration 🔄
```bash
# Create migration for new models
flask db migrate -m "Add security models: AuditLog, DeletedContent"

# Review migration file before applying
# Then upgrade
flask db upgrade
```

**Models Being Added:**
- `AuditLog` - Security audit trail
- `DeletedContent` - Content recovery archive

**Estimated Time:** 5 minutes

---

### 3. Environment Configuration ✅

Add to `.env`:
```
# Security
WTF_CSRF_ENABLED=true
WTF_CSRF_TIME_LIMIT=None

# Rate Limiting
RATELIMIT_STORAGE_URL=memory://  # Use Redis in production

# File Upload
UPLOAD_FOLDER=uploads
MAX_CONTENT_LENGTH=104857600  # 100MB

# Session Security
PERMANENT_SESSION_LIFETIME=2592000  # 30 days
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=Lax
SESSION_COOKIE_SECURE=true  # Only in production with HTTPS

# Audit Logging
AUDIT_LOG_LEVEL=INFO
```

---

## TESTING PROCEDURES

### A. CSRF Protection Testing

**Test 1: Form Submission with CSRF Token**
```bash
1. Open browser to http://localhost:5000/blog/create
2. Inspect HTML - verify _csrf_token field exists
3. Submit form normally
4. Should succeed ✅
```

**Test 2: Form Submission without CSRF Token**
```bash
1. Use curl to POST without CSRF token
   curl -X POST http://localhost:5000/blog/1/delete
2. Should get 400 Bad Request ✅
```

**Test 3: AJAX Request with CSRF Header**
```javascript
// In browser console
fetch('/messages/send', {
    method: 'POST',
    headers: {
        'X-CSRFToken': document.querySelector('[name=csrf_token]').value
    },
    body: new FormData(document.querySelector('form'))
})
```

---

### B. File Upload Security Testing

**Test 1: Reject Executable Files**
```bash
# Create fake .exe file
echo "MZ" | xxd -r -p > test.exe

# Try to upload as avatar
# Should reject with message ✅
```

**Test 2: Reject Oversized Files**
```bash
# Create 20MB image (larger than 5MB avatar limit)
dd if=/dev/zero bs=1M count=20 of=large.jpg

# Try to upload as avatar
# Should reject as too large ✅
```

**Test 3: Reject Wrong File Type**
```bash
# Upload .txt file as image
echo "Not an image" > fake.txt

# Rename to .jpg
mv fake.txt fake.jpg

# Try to upload
# Should reject (MIME type check fails) ✅
```

**Test 4: Accept Valid Image**
```bash
# Use real image
curl -F "file=@valid_image.jpg" http://localhost:5000/uploads/avatars/

# Should succeed ✅
```

---

### C. Audit Logging Testing

**Test 1: Verify Login Audit**
```bash
1. Log in to application
2. Open Flask shell: flask shell
3. Check logs:
   from app.models import AuditLog
   AuditLog.query.filter_by(event_type='login_success').first()
4. Should return entry ✅
```

**Test 2: Verify File Upload Audit**
```bash
1. Upload a file
2. Check database:
   flask shell
   AuditLog.query.filter_by(event_type='file_uploaded').all()
3. Should show upload record ✅
```

**Test 3: Verify Deletion Audit**
```bash
1. Create and delete content
2. Check:
   AuditLog.query.filter_by(event_type='content_deleted').all()
3. Should show deletion ✅
```

---

### D. Soft Delete Testing

**Test 1: Verify Content Archived**
```bash
1. Delete a blog post
2. Check archive:
   flask shell
   from app.models import DeletedContent
   DeletedContent.query.first()
3. Should have archived copy ✅
```

**Test 2: Verify Recovery Capability**
```bash
1. Check recovery window:
   deleted = DeletedContent.query.first()
   deleted.can_recover()  # Should be True ✅
```

**Test 3: Verify 30-Day Expiration**
```bash
1. Create old archive (simulate 31 days old)
2. Check:
   deleted = DeletedContent.query.first()
   deleted.can_recover()  # Should be False ✅
```

---

### E. Password Confirmation Testing

**Test 1: Delete Without Password**
```bash
1. Try to delete blog post
2. Should be prompted for password ✅
3. Press "Cancel"
4. Should return to blog page ✅
```

**Test 2: Delete With Wrong Password**
```bash
1. Try to delete blog post
2. Enter wrong password
3. Should show "Invalid password" error ✅
```

**Test 3: Delete With Correct Password**
```bash
1. Try to delete blog post
2. Enter correct password
3. Should proceed with deletion ✅
```

---

### F. Account Deletion Testing

**Test 1: Account Deletion Flow**
```bash
1. Go to /delete-account
2. Review warning message
3. Uncheck confirmation → Try to submit → Should fail ✅
4. Check confirmation
5. Enter wrong password → Should fail ✅
6. Enter correct password → Should succeed ✅
7. User redirected to login ✅
8. Verify account deleted:
   flask shell
   User.query.filter_by(username='testuser').first()  # Should be None ✅
```

**Test 2: User Data Cleanup**
```bash
1. Delete account
2. Check deleted files:
   os.path.exists(f'uploads/avatars/{avatar_filename}')  # False ✅
3. Check soft-deleted content:
   DeletedContent.query.filter_by(deleted_by_username='testuser').count()  # > 0 ✅
```

---

### G. Security Headers Testing

**Test 1: Check Security Headers**
```bash
curl -i http://localhost:5000/blog

# Check for:
# X-Content-Type-Options: nosniff ✅
# X-Frame-Options: SAMEORIGIN ✅
# Content-Security-Policy: ... ✅
# Strict-Transport-Security: ... (production only) ⚠️
```

---

### H. Rate Limiting Testing

**Test 1: Basic Rate Limit**
```bash
# Make multiple requests
for i in {1..10}; do
  curl -X POST http://localhost:5000/messages/send
done

# After limit exceeded, should get 429 status ✅
```

---

## MANUAL TESTING SCENARIOS

### Scenario 1: Create and Delete Blog
```
1. Create blog post with thumbnail
   ✅ File uploaded and validated
   ✅ Audit log created
   
2. Edit blog with new thumbnail
   ✅ Old file deleted
   ✅ New file uploaded and validated
   
3. Delete blog
   ✅ Prompted for password
   ✅ Content archived
   ✅ File deleted from storage
   ✅ Audit log created
```

### Scenario 2: Full Account Lifecycle
```
1. Register new account
   ✅ Account created
   ✅ Email verification required
   
2. Upload profile picture
   ✅ MIME type validated
   ✅ Image resized
   ✅ Audit logged
   
3. Create content (blogs, projects)
   ✅ All uploads validated
   ✅ Audit logged
   
4. Delete account
   ✅ Password confirmed
   ✅ All content soft-deleted
   ✅ Files cleaned up
   ✅ Account removed
   ✅ Redirected to login
```

---

## AUTOMATED TEST SUITE

Create test file: `tests/test_security_phase1.py`

```python
import pytest
from app import create_app, db
from app.models import User, Blog, AuditLog, DeletedContent

class TestCSRFProtection:
    def test_csrf_token_required_for_delete(self, client, user):
        response = client.post(f'/blog/1/delete', data={})
        assert response.status_code == 400  # CSRF failure

class TestFileUpload:
    def test_reject_executable_files(self, client, user):
        with open('test.exe', 'wb') as f:
            f.write(b'MZ')  # Exe header
        with open('test.exe', 'rb') as f:
            response = client.post('/upload/avatar', data={
                'file': f
            })
        assert b'not allowed' in response.data

class TestAuditLogging:
    def test_login_audit_logged(self, client):
        client.post('/login', data={'email': 'user@example.com', 'password': 'pass'})
        audit = AuditLog.query.filter_by(event_type='login_success').first()
        assert audit is not None

class TestSoftDelete:
    def test_blog_archived_on_delete(self, client, user, blog):
        client.post(f'/blog/{blog.id}/delete', data={'password': 'password'})
        deleted = DeletedContent.query.first()
        assert deleted is not None
        assert deleted.content_type == 'blog'

class TestPasswordConfirmation:
    def test_delete_without_password(self, client, user):
        response = client.post(f'/blog/1/delete', data={})
        assert b'password' in response.data.lower()

class TestAccountDeletion:
    def test_account_deleted_with_password(self, client, user):
        response = client.post('/delete-account', data={
            'password': 'password',
            'confirm_delete': 'on'
        })
        assert User.query.get(user.id) is None
```

Run tests:
```bash
pytest tests/test_security_phase1.py -v
```

---

## PRODUCTION DEPLOYMENT CHECKLIST

Before deploying to production:

### Security
- [ ] HTTPS enabled
- [ ] SECRET_KEY changed from default
- [ ] WTF_CSRF_TIME_LIMIT configured
- [ ] Session cookies SECURE flag enabled
- [ ] HSTS header configured
- [ ] CSP header tuned
- [ ] Rate limiting using Redis (not memory)
- [ ] Audit logging enabled
- [ ] Database backups automated

### Performance
- [ ] Database indices created for audit logs
- [ ] File upload limits appropriate
- [ ] Rate limiting configured
- [ ] Caching strategy in place
- [ ] Load testing completed

### Monitoring
- [ ] Error logging configured
- [ ] Audit log monitoring
- [ ] Performance metrics collected
- [ ] Alerts set up for security events

### Documentation
- [ ] Security features documented
- [ ] Admin guide updated
- [ ] User guide updated
- [ ] Incident response plan ready

---

## ROLLBACK PROCEDURE

If issues occur:

```bash
# 1. Revert database migration
flask db downgrade

# 2. Revert code changes (git)
git revert HEAD

# 3. Restart application
supervisor ctl restart authflow

# 4. Verify
curl http://localhost:5000/health
```

---

## MONITORING & MAINTENANCE

### Daily Checks
```bash
# Check audit logs for suspicious activity
flask shell
from app.models import AuditLog
AuditLog.query.filter_by(event_type='login_failed').filter(AuditLog.created_at > datetime.utcnow() - timedelta(hours=24)).all()

# Check deleted content expiration
from app.models import DeletedContent
from datetime import datetime
expired = DeletedContent.query.filter(DeletedContent.expires_at < datetime.utcnow()).all()
print(f"Expired archives: {len(expired)}")
```

### Weekly Tasks
- [ ] Review audit logs
- [ ] Check for failed login attempts
- [ ] Verify file uploads
- [ ] Clean up expired archives
- [ ] Test disaster recovery

### Monthly Tasks
- [ ] Review security policies
- [ ] Update dependencies
- [ ] Security scanning
- [ ] Access review
- [ ] Backup verification

---

## SUPPORT & ESCALATION

If issues occur:

1. **CSRF Failures**
   - Check: Is Flask-WTF loaded?
   - Check: Are forms including csrf_token?
   - Check: Is AJAX using X-CSRFToken header?

2. **File Upload Issues**
   - Check: Is python-magic installed?
   - Check: Are file sizes within limits?
   - Check: Is folder in ALLOWED_FOLDERS?

3. **Audit Log Failures**
   - Check: Is database available?
   - Check: Are permissions correct?
   - Check: Is disk space available?

4. **Password Confirmation Issues**
   - Check: Is session working?
   - Check: Is timeout appropriate?
   - Check: Are templates rendering?

---

**Phase 1 Complete!** 🎉

**Next Steps:** Begin Phase 2 (RBAC, API Security, XSS Protection)

---

**Support Contact:** [security-team@authflow.local]
