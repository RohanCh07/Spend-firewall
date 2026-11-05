FROM node:22-alpine AS build
WORKDIR /repo
RUN corepack enable
COPY . .
RUN pnpm install && pnpm --filter spendfirewall build && pnpm --filter spendfirewall-dashboard build

FROM nginx:alpine
COPY --from=build /repo/dashboard/dist /usr/share/nginx/html
