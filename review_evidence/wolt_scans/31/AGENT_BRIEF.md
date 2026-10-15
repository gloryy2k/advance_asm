# AGENT BRIEF — wolt
Scan 31 · light · done_partial
Nguồn scope: Trang công khai HackerOne — chưa xác minh bằng API — đọc policy chính thức trước khi hunt

## SCOPE
# IN
*.wolt.com
authentication.wolt.com
corporate.wolt.com
drive.wolt.com
merchant.wolt.com
ops.wolt.com
restaurant-api.wolt.com
wolt.com
com.wolt.android
com.wolt.courierapp
1477299281
943905271
# OUT
*.pipedrive.com
gettest.wolt.com
https://merchant.wolt.com/api/merchant-onboarding/merchant-admin/inbound-merchant
https://restaurant-api.wolt.com/v1/waw-api/corporate-leads
https://merchant-onboarding-service.wolt.com/merchant-admin/inbound-merchant
https://wolt.com/en/wolt-for-work-contact-request
https://merchant.wolt.com/app/partner-with-wolt
https://wolt.typeform.com
wolt.atlassian.net
press.wolt.com
links.wolt.com
blog.wolt.com

## SỐ LIỆU
Assets: 753 · Live: 4 · URLs: 227 · Findings: 0

Scan có dữ liệu một phần; không suy ra host vắng là đã biến mất.

## TOP SURFACE
|Host|Rank|Status|Tech|Lý do|
|---|---:|---|---|---|
|account.converse-api-dd.wolt.com|6|-|-|api, auth, fresh|
|cdnbhscmpicker-api-merchant-admin.util.wolt.com|6|-|-|api, auth, fresh|
|corporate.wolt.com|5.5|200|Amazon CloudFront, Amazon S3, Amazon Web Services, +5|auth, fresh, tech_risk, express, s3, status_200|
|daas-internal-api.wolt.com|5|-|-|api, fresh, nonproduction|
|r-api-grpc-internal.wolt.com|5|-|-|api, fresh, nonproduction|
|www.daas-internal-api.wolt.com|5|-|-|api, fresh, nonproduction|
|account-2019.account-beta-status-internal.util.wolt.com|4.5|-|-|auth, fresh, nonproduction|
|beta-accessy.account.dev.internal.util.wolt.com|4.5|-|-|auth, fresh, nonproduction|
|api.wolt.com|4|-|-|api, fresh|
|app.converse-telemetry-api.wolt.com|4|-|-|api, fresh|
|atlas-api.wolt.com|4|-|-|api, fresh|
|authentication.wolt.com|4|404|Amazon CloudFront, Amazon Web Services|api, fresh|
|autoconfig.converse-api-dd.wolt.com|4|-|-|api, fresh|
|aws.consumer-api.wolt.com|4|-|-|api, fresh|
|cdn.converse-rtm-api.wolt.com|4|-|-|api, fresh|
|ci-ecom-v1.util.wolt.com|4|-|-|api, fresh|
|click.consumer-api.wolt.com|4|-|-|api, fresh|
|cm-daas-self-service-api-corp.util.wolt.com|4|-|-|api, fresh|
|cmpicker-api-merchant-adminsignedu.util.wolt.com|4|-|-|api, fresh|
|cmpicker-api-merchant-appsinu.util.wolt.com|4|-|-|api, fresh|
|cmpicker-api-merchant-mobilek.util.wolt.com|4|-|-|api, fresh|
|consumer-api-experiment.wolt.com|4|-|-|api, fresh|
|consumer-api.wolt.com|4|-|-|api, fresh|
|converse-api-dd.wolt.com|4|-|-|api, fresh|
|converse-api.util.wolt.com|4|-|-|api, fresh|

## ENDPOINT ĐÁNG XEM
URL: 4422 từ tool → 223 trong scope (4182 ngoài scope bị loại). Dữ liệu từ archive là LỊCH SỬ, chưa kiểm chứng.
- [5] https://consumer-api.wolt.com/consumer-api/consumer-assortment/v1/venues/slug/$ — api, auth · lịch sử
- [3] https://api.wolt.com/v1/fetch — api · lịch sử
- [3] https://authentication.wolt.com/v1/wauth2/consumer — api · lịch sử
- [3] https://authentication.wolt.com/v1/wauth2/me/request_number_verification — api · lịch sử
- [3] https://authentication.wolt.com/v2/wauth2/me/request_number_verification — api · lịch sử
- [3] https://developer.wolt.com/docs/api — api · lịch sử
- [3] https://developer.wolt.com/docs/api/order — api · lịch sử
- [3] https://gatekeeper.wolt.com/v1/merchant_admin — api · lịch sử
- [2.5] https://corporate.wolt.com/oauth2/ — auth · lịch sử
- [2.5] https://explore.wolt.com/az/aze/wolt-drive/signup/thank-you — auth · lịch sử
- [2.5] https://explore.wolt.com/bg/bgr/wolt-drive/signup/thank-you — auth · lịch sử
- [2.5] https://explore.wolt.com/cs/cze/wolt-drive/signup/thank-you — auth · lịch sử

## ASSET MỚI
- account.converse-api-dd.wolt.com
- cdnbhscmpicker-api-merchant-admin.util.wolt.com
- corporate.wolt.com
- daas-internal-api.wolt.com
- r-api-grpc-internal.wolt.com
- www.daas-internal-api.wolt.com
- account-2019.account-beta-status-internal.util.wolt.com
- beta-accessy.account.dev.internal.util.wolt.com
- api.wolt.com
- app.converse-telemetry-api.wolt.com
- atlas-api.wolt.com
- authentication.wolt.com
- autoconfig.converse-api-dd.wolt.com
- aws.consumer-api.wolt.com
- cdn.converse-rtm-api.wolt.com
- ci-ecom-v1.util.wolt.com
- click.consumer-api.wolt.com
- cm-daas-self-service-api-corp.util.wolt.com
- cmpicker-api-merchant-adminsignedu.util.wolt.com
- cmpicker-api-merchant-appsinu.util.wolt.com
- cmpicker-api-merchant-mobilek.util.wolt.com
- consumer-api-experiment.wolt.com
- consumer-api.wolt.com
- converse-api-dd.wolt.com
- converse-api.util.wolt.com
- converse-api.wolt.com
- converse-rtm-api.wolt.com
- converse-suggestions-proxy-api.wolt.com
- converse-telemetry-api.wolt.com
- converse-upload-api.wolt.com
- … và 723 asset mới khác (xem dashboard / recon/scans/31/)

## SIGNALS
- Manual [mobile]: com.wolt.android; mobile: mobile-pentest.
- Manual [mobile]: com.wolt.courierapp; mobile: mobile-pentest.
- Manual [mobile]: 1477299281; mobile: mobile-pentest.
- Manual [mobile]: 943905271; mobile: mobile-pentest.
- Intel không khả dụng; không ảnh hưởng recon.

## HƯỚNG TEST
- account.converse-api-dd.wolt.com: kiểm tra phân quyền/IDOR và rate limit ở endpoint API; xem luồng đăng nhập/SSO/reset mật khẩu; asset mới, chưa ai nhìn kỹ
- cdnbhscmpicker-api-merchant-admin.util.wolt.com: kiểm tra phân quyền/IDOR và rate limit ở endpoint API; xem luồng đăng nhập/SSO/reset mật khẩu; asset mới, chưa ai nhìn kỹ
- corporate.wolt.com: xem luồng đăng nhập/SSO/reset mật khẩu; asset mới, chưa ai nhìn kỹ; tech có tiền sử lỗi; đối chiếu phiên bản
- daas-internal-api.wolt.com: kiểm tra phân quyền/IDOR và rate limit ở endpoint API; asset mới, chưa ai nhìn kỹ; môi trường dev/staging thường lỏng hơn prod
- r-api-grpc-internal.wolt.com: kiểm tra phân quyền/IDOR và rate limit ở endpoint API; asset mới, chưa ai nhìn kỹ; môi trường dev/staging thường lỏng hơn prod

## GHI CHÚ SCOPE
- IN *.wolt.com: Anything else under the `.wolt.com` domain is fair game with some exceptions (see the out of scope items). Depending on the affected service and findi
- IN authentication.wolt.com: Keywords: OAuth2, OIDC, JWT * Used by: Regular wolt.com users, Wolt employees, other services (service-to-service communication). * Handles the vast m
- IN corporate.wolt.com: Keywords: admin * Used by: Wolt employees, corporate customers. * Admin portal for Wolt's corporate customers. * Your JWT as a regular wolt.com user s
- IN drive.wolt.com: Keywords: admin * Used by: Wolt employees, delivery partners. * Admin portal for Wolt's last-mile delivery partners. * Your JWT as a regular wolt.com 
- IN merchant.wolt.com: Keywords: admin * Used by: Wolt employees, store managers. * Portal for store managers to update menus. * Your JWT as a regular wolt.com user should g
- IN ops.wolt.com: Keywords: admin * Used by: Wolt employees. * This service's endpoints are only accessible by Wolt employees (if you can show otherwise, that’ll be ver
- IN restaurant-api.wolt.com: * Used by: Regular wolt.com users, Wolt employees, corporate customers, delivery partners, store managers. * Notable use-cases: Creating and editing u
- IN wolt.com: Used by: Everybody. * Our main web page. * Notable use-cases: Offering an in-browser JavaScript app to interact with other APIs and services. Offering
- IN com.wolt.android: Wolt  Customer Android app: https://play.google.com/store/apps/details?id=com.wolt.android  Notable use-cases: Regular wolt.com account creation, plac
- IN com.wolt.courierapp: Wolt Courier Partner Android app: https://play.google.com/store/apps/details?id=com.wolt.courierapp  * Notable use-cases: Receiving delivery requests,
- IN 1477299281: Wolt Courier Partner iOS app: https://apps.apple.com/app/1477299281  * Notable use-cases: Receiving delivery requests, tracking orders, completing del
- IN 943905271: Wolt Customer iOS app: https://apps.apple.com/app/943905271  Notable use-cases: Regular wolt.com account creation, placing orders, tracking your order
- OUT *.pipedrive.com: Any Pipedrive forms linked from *.wolt.com domains are out of scope.
- OUT https://merchant.wolt.com/api/merchant-onboarding/merchant-admin/inbound-merchan: Do not POST data here, as it will be sent to a third-party system that is also out of scope.
- OUT https://restaurant-api.wolt.com/v1/waw-api/corporate-leads: Do not POST data here, as it will be sent to a third-party system that is also out of scope.
- OUT https://merchant-onboarding-service.wolt.com/merchant-admin/inbound-merchant: Do not POST data here, as it will be sent to a third-party system that is also out of scope.
- OUT https://wolt.typeform.com: Any Typeform forms linked from *.wolt.com domains are out of scope.
- OUT press.wolt.com: This is a third-party SaaS and we aren't authorized to test it.
- OUT blog.wolt.com: Keywords: Third-party SaaS, WordPress * Used by: Wolt employees. * WordPress blog hosted by wpengine.com. wpengine.com owns the infrastructure, but we

## CÁCH LÀM VIỆC
Đọc PROGRAM.md để biết policy; dữ liệu recon ở recon/scans/31/. Ghi chú vào notes/, findings/ và reports/. Không tự submit.
