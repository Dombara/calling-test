# Twilio CLI Configuration Commands

## Install Twilio CLI (if not installed)
```bash
npm install -g twilio-cli
```

## Login to Twilio
```bash
twilio login
```

## Update Phone Number Configuration
Replace YOUR_PHONE_NUMBER with your actual Twilio phone number (format: +1234567890)

```bash
twilio api:core:incoming-phone-numbers:update \
  --sid YOUR_PHONE_NUMBER_SID \
  --voice-url https://calling-test-2kdd.onrender.com/voice \
  --voice-method POST
```

## List your phone numbers to get the SID
```bash
twilio api:core:incoming-phone-numbers:list
```

## Test the configuration
```bash
curl -X POST https://calling-test-2kdd.onrender.com/voice
```