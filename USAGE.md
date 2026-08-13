# Usage Guide: Alterna Mobile (ALTM) Backend

This guide provides instructions on how to interact with the core features of the ALTM backend API, focusing on the authentication and authorization module.

## 1. Authentication

The authentication system is designed with a high level of security, incorporating features like refresh token rotation, device fingerprinting, and step-up authentication for sensitive operations.

### 1.1. User Login

To log in, a client must send a POST request to the `/api/v1/auth/login` endpoint. The request body must include the user's credentials and a device fingerprint.

**Endpoint:** `POST /api/v1/auth/login`

**Request Body:**

```json
{
  "username": "user@example.com",
  "password": "user_password",
  "device_fingerprint": {
    "device_id": "unique_device_uuid_or_fingerprint",
    "os_name": "iOS",
    "os_version": "17.0",
    "ip_address": "203.0.113.1",
    "user_agent": "AlternaMobile/1.0.0 (iPhone15,2; iOS 17.0; Scale/3.00)"
  }
}
```

**Successful Response (200 OK):**

A successful login returns an access token and a refresh token.

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Error Responses:**
- `401 Unauthorized`: Invalid credentials, weak password, or a locked account. The response time is constant to prevent user enumeration attacks.
- `428 Precondition Required`: The login is from an untrusted device. The user must verify the new device through an out-of-band notification (e.g., email link) before the session can proceed.

### 1.2. Refreshing an Access Token

When the access token expires, the client can obtain a new one using the refresh token. This mechanism uses Refresh Token Rotation (RTR), meaning each refresh request returns a *new* refresh token and invalidates the one used.

**Endpoint:** `POST /api/v1/auth/refresh`

**Request Body:**

```json
{
  "refresh_token": "the_refresh_token_received_at_login"
}
```

**Successful Response (200 OK):**

Returns a new pair of access and refresh tokens.

```json
{
  "access_token": "a_new_access_token...",
  "refresh_token": "a_new_refresh_token...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Important:** If a refresh token is ever reused, the entire session family is immediately revoked, and all devices are logged out as a security precaution.

## 2. Step-Up Authentication

For critical operations like registering a new beneficiary or requesting a withdrawal, the API requires step-up authentication. This process links a one-time token to the exact hash of the transaction payload.

### Step 1: Request a Step-Up Token

Before executing a sensitive action, the client must request a step-up token.

**Endpoint:** `POST /api/v1/auth/step-up`

**Request Body:**

The body must contain the exact payload of the operation you intend to perform.

```json
{
  "operation": "REGISTER_BENEFICIARY",
  "details": {
    "clabe": "032180000118359719",
    "beneficiary_name": "Jane Doe"
  }
}
```

**Successful Response (200 OK):**

The API returns a step-up token after sending an MFA code (e.g., via Push Notification or TOTP) to the user.

```json
{
  "step_up_token": "a_unique_single_use_step_up_token"
}
```

### Step 2: Execute the Operation

Include the received `step_up_token` and the user's MFA code in the request for the sensitive operation.

**Example Endpoint:** `POST /api/v1/money/beneficiaries`

**Request Body:**

```json
{
  "clabe": "032180000118359719",
  "beneficiary_name": "Jane Doe",
  "mfa_code": "123456",
  "step_up_token": "the_step_up_token_from_previous_step"
}
```

If the `step_up_token` is valid and the hash of the payload matches the one it was created for, the operation will be processed.
